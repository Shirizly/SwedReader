"""Step 4 debug script: word alignment from Marian cross-attention.

Usage: 04_align.py [mean|<layer index>] ["Swedish sentence" ...]
Prints, for each Swedish word, the English words whose attention peaks on it.
"""
import re
import sys

import spacy
import torch
from transformers import MarianMTModel, MarianTokenizer

from pipeline.segment import tokens_from_doc

MODEL = "Helsinki-NLP/opus-mt-sv-en"
MODE = sys.argv[1] if len(sys.argv) > 1 else "4"
SENTENCES = sys.argv[2:] or [
    "Idag bor jag i Stockholm.",
    "Bilen står på gatan.",
    "Han gav upp.",
    "Tågstationen är stor.",
    "Stockholm är Sveriges huvudstad och största stad.",
    "Hon ska gå till affären i morgon.",
    "Staden anses traditionellt ha grundats i mitten av 1200-talet av Birger jarl.",
    "Innerstaden fick sin karaktär av Lindhagenplanen från 1866.",
]

nlp = spacy.load("sv_core_news_sm")
tok = MarianTokenizer.from_pretrained(MODEL)
model = MarianMTModel.from_pretrained(MODEL, attn_implementation="eager").eval()


def translate(text):
    batch = tok([text], return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**batch, num_beams=4, max_length=256)
    return tok.batch_decode(out, skip_special_tokens=True)[0]


def piece_spans(pieces, text):
    """Character span of each sentencepiece in text (None for special/unknown pieces)."""
    spans, pos = [], 0
    for p in pieces:
        s = p.replace("▁", "")
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if p in tok.all_special_tokens or not s or not text.startswith(s, pos):
            spans.append(None)
        else:
            spans.append((pos, pos + len(s)))
            pos += len(s)
    return spans


def word_index(spans, words):
    """For each piece, index of the word whose span contains the piece start."""
    idx = []
    for sp in spans:
        idx.append(None if sp is None else next((i for i, (a, b) in enumerate(words) if a <= sp[0] < b), None))
    return idx


def align(src_text, tokens, tgt_text):
    # source words = spaCy tokens with char spans in the reconstructed text
    pos, src_words = 0, []
    for t in tokens:
        src_words.append((pos, pos + len(t["text"])))
        pos += len(t["text"]) + len(t["ws"])
    tgt_words = [(m.start(), m.end()) for m in re.finditer(r"\w+(?:['’]\w+)?|[^\w\s]", tgt_text)]

    enc = tok([src_text], return_tensors="pt")
    labels = tok(text_target=[tgt_text], return_tensors="pt").input_ids
    with torch.no_grad():
        out = model(**enc, labels=labels, output_attentions=True)
    ca = torch.stack(out.cross_attentions)[:, 0]  # (layers, heads, tgt, src)
    A = ca.mean((0, 1)) if MODE == "mean" else ca[int(MODE)].mean(0)
    A = A[:, :-1]  # drop source </s>
    A = A / A.sum(-1, keepdim=True)

    src_pieces = tok.convert_ids_to_tokens(enc.input_ids[0])
    tgt_pieces = tok.convert_ids_to_tokens(labels[0])
    s_idx = word_index(piece_spans(src_pieces, src_text), src_words)
    t_idx = word_index(piece_spans(tgt_pieces, tgt_text), tgt_words)

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

    # Backward pass: a source word with no English word joins the source word that owns the
    # English word it attends to most, forming a many-to-many group.
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
    groups = {}
    for i in range(len(src_words)):
        groups.setdefault(find(i), []).append(i)
    groups = [sorted(m) for m in groups.values() if len(m) > 1 and len(m) <= 4]
    return src_words, tgt_words, result, groups


for text in SENTENCES:
    tokens = tokens_from_doc(nlp(text))
    src_text = "".join(t["text"] + t["ws"] for t in tokens).rstrip()
    tr = translate(src_text)
    src_words, tgt_words, result, groups = align(src_text, tokens, tr)
    print(f"\nSV: {src_text}\nEN: {tr}")
    for i, t in enumerate(tokens):
        eng = " ".join(tr[tgt_words[j][0]:tgt_words[j][1]] for j in result[i])
        print(f"  {t['text']:<22} -> {eng}")
    for g in groups:
        js = sorted(j for i in g for j in result[i])
        print("  GROUP:", " ".join(tokens[i]["text"] for i in g), "=>",
              " ".join(tr[tgt_words[j][0]:tgt_words[j][1]] for j in js))
