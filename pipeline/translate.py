"""Sentence translation (OPUS-MT) and word alignment from its cross-attention.

The rest of the pipeline only depends on the Translator interface (translate + align), so another
engine can be swapped in without changing the document format.
"""
import re

import torch

from .qa import GAP

MODEL = "Helsinki-NLP/opus-mt-sv-en"
ALIGN_LAYER = 4  # decoder layer whose cross-attention aligns best (all-layer mean shifts onto neighbours)
MAX_GROUP = 4


def join_target_words(indices, words, text):
    """English text for aligned target-word indices; non-adjacent pieces are separated by a gap marker."""
    out, prev = [], None
    for j in sorted(set(indices)):
        if prev is not None and j != prev + 1:
            out.append(GAP)
        out.append(text[words[j][0]:words[j][1]])
        prev = j
    return " ".join(out)


class OpusMtTranslator:
    name = f"{MODEL}"

    def __init__(self, device=None, batch_size=16):
        from transformers import MarianMTModel, MarianTokenizer
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = batch_size
        self.tok = MarianTokenizer.from_pretrained(MODEL)
        self.model = MarianMTModel.from_pretrained(MODEL, attn_implementation="eager").to(self.device).eval()

    def translate(self, sentences):
        out = []
        for i in range(0, len(sentences), self.batch_size):
            batch = self.tok(sentences[i:i + self.batch_size], return_tensors="pt", padding=True,
                             truncation=True, max_length=256).to(self.device)
            with torch.no_grad():
                gen = self.model.generate(**batch, num_beams=4, max_length=256)
            out.extend(self.tok.batch_decode(gen, skip_special_tokens=True))
        return out

    def translate_words(self, words):
        """Translate isolated words/lemmas (no context, so only a fallback). Returns one string per input."""
        out = []
        for i in range(0, len(words), 64):
            chunk = words[i:i + 64]
            batch = self.tok(chunk, return_tensors="pt", padding=True, truncation=True, max_length=32).to(self.device)
            with torch.no_grad():
                gen = self.model.generate(**batch, num_beams=4, max_length=24)
            for src, tr in zip(chunk, self.tok.batch_decode(gen, skip_special_tokens=True)):
                tr = tr.strip().rstrip(".").strip()
                if src.islower() and tr[:1].isupper() and not tr.isupper():
                    tr = tr[0].lower() + tr[1:]
                out.append(tr)
        return out

    def _piece_spans(self, pieces, text):
        spans, pos = [], 0
        for p in pieces:
            s = p.replace("▁", "")
            while pos < len(text) and text[pos].isspace():
                pos += 1
            if p in self.tok.all_special_tokens or not s or not text.startswith(s, pos):
                spans.append(None)
            else:
                spans.append((pos, pos + len(s)))
                pos += len(s)
        return spans

    @staticmethod
    def _word_index(spans, words):
        return [None if sp is None else next((i for i, (a, b) in enumerate(words) if a <= sp[0] < b), None)
                for sp in spans]

    def align(self, src_text, tokens, tgt_text):
        """Return (in_context, groups): in_context[i] is the English text aligned to token i ('' if none);
        groups are {'token_ids': [...], 'in_context': str} for many-to-many links."""
        pos, src_words = 0, []
        for t in tokens:
            src_words.append((pos, pos + len(t["text"])))
            pos += len(t["text"]) + len(t["ws"])
        tgt_words = [(m.start(), m.end()) for m in re.finditer(r"\w+(?:['’]\w+)?|[^\w\s]", tgt_text)]
        if not tgt_words:
            return [""] * len(tokens), []

        enc = self.tok([src_text], return_tensors="pt", truncation=True, max_length=256).to(self.device)
        labels = self.tok(text_target=[tgt_text], return_tensors="pt", truncation=True,
                          max_length=256).input_ids.to(self.device)
        with torch.no_grad():
            out = self.model(**enc, labels=labels, output_attentions=True)
        A = torch.stack(out.cross_attentions)[ALIGN_LAYER, 0].mean(0).float().cpu()  # (tgt, src)
        A = A[:, :-1]  # drop source </s>
        A = A / A.sum(-1, keepdim=True)

        src_pieces = self.tok.convert_ids_to_tokens(enc.input_ids[0])
        tgt_pieces = self.tok.convert_ids_to_tokens(labels[0])
        s_idx = self._word_index(self._piece_spans(src_pieces, src_text), src_words)
        t_idx = self._word_index(self._piece_spans(tgt_pieces, tgt_text), tgt_words)

        S = torch.zeros(A.shape[0], len(src_words))
        for sp, wi in enumerate(s_idx[:-1]):
            if wi is not None:
                S[:, wi] += A[:, sp]
        tgt_to_src, n_pieces = {}, {}
        for tp, wj in enumerate(t_idx):
            if wj is not None:
                tgt_to_src.setdefault(wj, torch.zeros(len(src_words)))
                tgt_to_src[wj] += S[tp]
                n_pieces[wj] = n_pieces.get(wj, 0) + 1
        result = {i: [] for i in range(len(src_words))}
        for wj, vec in sorted(tgt_to_src.items()):
            result[int(vec.argmax())].append(wj)

        parent = list(range(len(src_words)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        owner = {wj: i for i, js in result.items() for wj in js}
        for i in range(len(src_words)):
            if result[i] or not tokens[i]["is_word"] or not tgt_to_src:
                continue
            best = max(tgt_to_src, key=lambda wj: float(tgt_to_src[wj][i]) / n_pieces[wj])
            if best in owner and tokens[owner[best]]["is_word"]:
                parent[find(i)] = find(owner[best])

        def words(js):
            return join_target_words(js, tgt_words, tgt_text)

        in_context = [words(result[i]) for i in range(len(src_words))]
        members = {}
        for i in range(len(src_words)):
            members.setdefault(find(i), []).append(i)
        groups = [{"token_ids": m, "in_context": words(j for i in m for j in result[i])}
                  for m in members.values() if 2 <= len(m) <= MAX_GROUP]
        return in_context, groups
