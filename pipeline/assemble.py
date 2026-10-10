"""Build, validate, and write the document JSON consumed by the reader."""
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

import jsonschema

from .qa import annotate_sentence
from .segment import segment, sentence_text

SCHEMA = {
    "type": "object",
    "required": ["id", "title", "source_url", "source_domain", "lane", "retrieved_at", "language_pair",
                 "word_count", "attribution", "license", "license_url", "history_url", "translator", "glossary",
                 "paragraphs"],
    "properties": {
        "lane": {"enum": ["public", "private"]},
        "word_count": {"type": "integer", "minimum": 0},
        "glossary": {"type": "object", "additionalProperties": {
            "type": "object", "properties": {"mt": {"type": "string"}, "dict": {"type": "array", "items": {"type": "string"}}}}},
        "author": {"type": "string"},
        "paragraphs": {"type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["sentences"], "properties": {
                "heading": {"type": ["string", "null"]},
                "sentences": {"type": "array", "minItems": 1, "items": {
                    "type": "object", "required": ["id", "text", "translation", "tokens", "groups"],
                    "properties": {
                        "tokens": {"type": "array", "minItems": 1, "items": {
                            "type": "object", "required": ["text", "lemma", "is_word", "ws"],
                            "properties": {"in_context": {"type": "string"}}}},
                        "groups": {"type": "array", "items": {
                            "type": "object", "required": ["token_ids", "in_context"]}},
                    }}}}}},
    },
}


def slugify(url):
    from urllib.parse import unquote, urlparse
    p = urlparse(url)
    return re.sub(r"[^a-z0-9åäö]+", "-", f"{p.hostname}{unquote(p.path)}".lower()).strip("-")


def _sentence(sid, toks, translation, in_context, groups):
    tokens = []
    for t, ctx in zip(toks, in_context):
        tok = dict(t)
        if ctx:
            tok["in_context"] = ctx
        tokens.append(tok)
    return {"id": sid, "text": sentence_text(toks), "translation": translation, "tokens": tokens, "groups": groups}


def clean_mt(lemma, text):
    """Sanitise an isolated-word machine translation; '' when it looks like junk (hallucinated repeats,
    sentences, or an untranslated copy of the input)."""
    text = text.strip().strip(".:;,!?\"' ").strip()
    if not text or len(text.split()) > 4 or re.search(r"[.!?]", text):
        return ""
    if text.lower() == lemma.lower() and lemma.islower() and len(lemma) > 3:
        return ""
    return text


def build_glossary(sentences, translator, dictionary=None):
    """Per lemma|pos: isolated machine translation ("mt") and dictionary glosses ("dict")."""
    keys = {}
    for s in sentences:
        for t in s["tokens"]:
            if t["is_word"]:
                keys.setdefault((t["lemma"], t.get("pos", "")), t["text"])
    lemma_list = sorted({lemma for lemma, _ in keys})
    mt = {lemma: clean_mt(lemma, tr) for lemma, tr in zip(lemma_list, translator.translate_words(lemma_list))}
    glossary = {}
    for (lemma, pos), surface in sorted(keys.items()):
        entry = {}
        if mt.get(lemma):
            entry["mt"] = mt[lemma]
        glosses = dictionary.lookup(lemma, pos, surface) if dictionary else []
        if glosses:
            entry["dict"] = glosses
        if entry:
            glossary[f"{lemma}|{pos}"] = entry
    return glossary


def build_document(url, lane_info, title, sections, nlp, translator, history_url="", author="",
                   dictionary=None, lemmas=None, progress=print):
    """Segment, translate, align, add word fallbacks and (if `lemmas` is given) QA flags."""
    title_tokens = [t for s in segment(nlp, title) for t in s]
    paragraphs, flat = [], [title_tokens]
    for heading, paras in sections:
        for k, text in enumerate(paras):
            sents = segment(nlp, text)
            paragraphs.append((heading if k == 0 else None, sents))
            flat.extend(sents)
    progress(f"{len(flat) - 1} sentences; translating...")
    translations = translator.translate([sentence_text(s) for s in flat])
    progress("aligning words...")

    aligned = []
    for i, (toks, tr) in enumerate(zip(flat, translations)):
        in_context, groups = translator.align(sentence_text(toks), toks, tr)
        aligned.append(_sentence("t" if i == 0 else f"s{i - 1}", toks, tr, in_context, groups))
        if i and i % 50 == 0:
            progress(f"  aligned {i}/{len(flat) - 1}")
    title_sentence, body = aligned[0], aligned[1:]

    progress("word translations and dictionary...")
    glossary = build_glossary(aligned, translator, dictionary)
    qa = None
    if lemmas:
        qa = Counter()
        for s in aligned:
            qa.update(annotate_sentence(s, glossary, lemmas))
        qa = dict(sorted(qa.items()))

    it = iter(body)
    doc_paragraphs = [{"heading": heading, "sentences": [next(it) for _ in sents]} for heading, sents in paragraphs]
    word_count = sum(t["is_word"] for s in body for t in s["tokens"])
    doc = {
        "id": slugify(url), "title": title, "author": author, "title_sentence": title_sentence,
        "source_url": url, "source_domain": lane_info["domain"], "lane": lane_info["lane"],
        "retrieved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "language_pair": "sv-en", "word_count": word_count, "attribution": lane_info["attribution"],
        "license": lane_info["license"], "license_url": lane_info["license_url"], "history_url": history_url,
        "translator": translator.name, "glossary": glossary, "paragraphs": doc_paragraphs,
    }
    if dictionary:
        doc["dictionary"] = dict(dictionary.info)
    if qa is not None:
        doc["qa"] = qa
    return doc


def validate(doc):
    jsonschema.validate(doc, SCHEMA)
    for p in doc["paragraphs"]:
        for s in p["sentences"]:
            for g in s["groups"]:
                if not all(0 <= i < len(s["tokens"]) for i in g["token_ids"]):
                    raise jsonschema.ValidationError(f"group token id out of range in {s['id']}")
    if doc["lane"] == "public" and not (doc["license"] and doc["license_url"] and doc["attribution"]):
        raise jsonschema.ValidationError("public documents need license, license_url and attribution")


def write_document(doc, directory):
    """Validate, then write atomically. Returns (path, sha256 of the file)."""
    validate(doc)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    data = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path = directory / f"{doc['id']}.json"
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path, hashlib.sha256(data).hexdigest()
