"""Build, validate, and write the document JSON consumed by the reader."""
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

import jsonschema

from .segment import segment, sentence_text

SCHEMA = {
    "type": "object",
    "required": ["id", "title", "source_url", "source_domain", "lane", "retrieved_at", "language_pair",
                 "word_count", "attribution", "license", "license_url", "history_url", "translator", "glossary",
                 "paragraphs"],
    "properties": {
        "lane": {"enum": ["public", "private"]},
        "word_count": {"type": "integer", "minimum": 0},
        "glossary": {"type": "object"},
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


def build_document(url, lane_info, title, sections, nlp, translator, history_url="", progress=print):
    paragraphs, flat = [], []
    for heading, paras in sections:
        for k, text in enumerate(paras):
            sents = segment(nlp, text)
            paragraphs.append((heading if k == 0 else None, sents))
            flat.extend(sents)
    progress(f"{len(flat)} sentences; translating...")
    translations = translator.translate([sentence_text(s) for s in flat])
    progress("aligning words...")

    n, word_count, doc_paragraphs = 0, 0, []
    for heading, sents in paragraphs:
        out = []
        for toks in sents:
            src = sentence_text(toks)
            in_context, groups = translator.align(src, toks, translations[n])
            tokens = []
            for t, ctx in zip(toks, in_context):
                tok = dict(t)
                if ctx:
                    tok["in_context"] = ctx
                tokens.append(tok)
            word_count += sum(t["is_word"] for t in toks)
            out.append({"id": f"s{n}", "text": src, "translation": translations[n], "tokens": tokens,
                        "groups": groups})
            n += 1
            if n % 50 == 0:
                progress(f"  aligned {n}/{len(flat)}")
        doc_paragraphs.append({"heading": heading, "sentences": out})
    return {
        "id": slugify(url), "title": title, "source_url": url, "source_domain": lane_info["domain"],
        "lane": lane_info["lane"], "retrieved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "language_pair": "sv-en", "word_count": word_count, "attribution": lane_info["attribution"],
        "license": lane_info["license"], "license_url": lane_info["license_url"], "history_url": history_url,
        "translator": translator.name, "glossary": {}, "paragraphs": doc_paragraphs,
    }


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
