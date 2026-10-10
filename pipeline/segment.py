"""Rule-based sentence segmentation on top of spaCy tokens.

The statistical parser sometimes splits mid-sentence (e.g. after a comma), so spaCy is used for
tokenization and lemmas only; sentence boundaries come from the rules below.
"""

TERMINAL = {".", "!", "?", "…", "...", "?!", "!?", "!!", "??"}
CLOSERS = {")", "]", "”", '"', "’", "»", "'"}
OPENERS = {"(", "[", "”", '"', "’", "»", "«", "'", "“", "‘"}
# Lemma fixes for function words the small model gets wrong.
LEMMA_OVERRIDES = {"det": "det", "de": "de", "dem": "de", "dom": "de"}


def tokens_from_doc(doc):
    """Convert a spaCy Doc to token dicts; whitespace-only tokens are folded into the previous ws."""
    tokens = []
    for t in doc:
        if t.is_space:
            if tokens:
                tokens[-1]["ws"] += t.text + t.whitespace_
            continue
        lemma = LEMMA_OVERRIDES.get(t.lower_, t.lemma_ or t.text) if t.is_alpha else (t.lemma_ or t.text)
        tokens.append({"text": t.text, "lemma": lemma, "is_word": t.is_alpha, "ws": t.whitespace_})
    return tokens


def _starts_sentence(token):
    text = token["text"]
    return text[0].isupper() or text[0].isdigit() or text in OPENERS


def split_sentences(tokens):
    """Split a token list into sentences. Breaks only after terminal punctuation (plus closers)
    followed by an uppercase/digit/opener token, or at a newline."""
    sentences, current = [], []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        current.append(tok)
        i += 1
        if "\n" in tok["ws"] and i < len(tokens) and tok["text"] in TERMINAL | CLOSERS:
            sentences.append(current)
            current = []
            continue
        if tok["text"] in TERMINAL:
            while i < len(tokens) and tokens[i]["text"] in CLOSERS | TERMINAL:
                current.append(tokens[i])
                i += 1
            if i >= len(tokens):
                break
            if "\n" in current[-1]["ws"] or _starts_sentence(tokens[i]):
                sentences.append(current)
                current = []
    if current:
        sentences.append(current)
    return sentences


def segment(nlp, paragraph):
    """Return a list of sentences, each a list of token dicts, for one paragraph."""
    return split_sentences(tokens_from_doc(nlp(paragraph)))


def sentence_text(tokens):
    return "".join(t["text"] + t["ws"] for t in tokens).strip()
