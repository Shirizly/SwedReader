"""HTML/JSON report of word meanings flagged by the QA comparison, for human review.

Reports are written under data/private/review/ (git-ignored) for every document, public or private.
"""
import html
import json
from pathlib import Path

from .config import ROOT

REVIEW_DIR = ROOT / "data" / "private" / "review"
ORDER = ("weak", "wide", "conflict", "diff")
TITLES = {
    "weak": "Aligned only to articles/pronouns/prepositions (the reader ignores this meaning)",
    "wide": "Aligned meaning is scattered or long and shares nothing with the fallbacks",
    "conflict": "No aligned meaning, and the machine translation and dictionary disagree",
    "diff": "Aligned meaning shares nothing with the fallbacks (often just a synonym or a polysemous word)",
}
CSS = """body{font-family:system-ui,sans-serif;max-width:70rem;margin:1rem auto;padding:0 1rem}
table{border-collapse:collapse;width:100%;margin-bottom:2rem}td,th{border:1px solid #ccc;padding:.3rem .5rem;
vertical-align:top;text-align:left}th{background:#f0f0f0}mark{background:#ffd966}.sv{font-size:1.05em}.en{color:#555}
.small{font-size:.85em;color:#666}"""


def sentences_of(doc):
    out = [doc["title_sentence"]] if doc.get("title_sentence") else []
    return out + [s for p in doc["paragraphs"] for s in p["sentences"]]


def collect(doc):
    """List of flagged items (one per flagged token or group)."""
    glossary, items = doc["glossary"], []

    def make(sentence, ids, status, aligned):
        toks = sentence["tokens"]
        entries = [glossary.get(f"{toks[i]['lemma']}|{toks[i].get('pos', '')}", {}) for i in ids]
        return {
            "status": status, "sentence": sentence["id"], "token_ids": ids,
            "words": " ".join(toks[i]["text"] for i in ids), "lemmas": [toks[i]["lemma"] for i in ids],
            "aligned": aligned, "mt": [e["mt"] for e in entries if e.get("mt")],
            "dict": [g for e in entries for g in e.get("dict", [])],
            "sv": sentence["text"], "en": sentence["translation"],
        }

    for s in sentences_of(doc):
        grouped = {i for g in s["groups"] for i in g["token_ids"]}
        for g in s["groups"]:
            if g.get("check"):
                items.append(make(s, g["token_ids"], g["check"], g["in_context"]))
        for i, t in enumerate(s["tokens"]):
            if t.get("check") and i not in grouped:
                items.append(make(s, [i], t["check"], t.get("in_context", "")))
    return aggregate(items)


def aggregate(items):
    """Merge identical findings (same status, lemmas and aligned meaning); keep the first example sentence."""
    merged = {}
    for it in items:
        key = (it["status"], tuple(it["lemmas"]), it["aligned"])
        if key in merged:
            merged[key]["count"] += 1
            merged[key]["also_in"].append(it["sentence"])
        else:
            merged[key] = {**it, "count": 1, "also_in": []}
    return list(merged.values())


def _sv_html(sentence_text, tokens_text, ids):
    """Sentence with the flagged tokens highlighted."""
    out = []
    for i, (text, ws) in enumerate(tokens_text):
        e = html.escape(text)
        out.append(f"<mark>{e}</mark>" if i in ids else e)
        out.append(html.escape(ws))
    return "".join(out)


def render(doc, items):
    by_id = {s["id"]: s for s in sentences_of(doc)}
    parts = [f"<!doctype html><meta charset='utf-8'><title>Review: {html.escape(doc['title'])}</title>",
             f"<style>{CSS}</style><h1>Review: {html.escape(doc['title'])}</h1>",
             f"<p class='small'>{html.escape(doc['id'])} &middot; translator {html.escape(doc['translator'])}</p>"]
    qa = doc.get("qa", {})
    parts.append("<p>Content words by status: " + ", ".join(f"<b>{k}</b> {v}" for k, v in qa.items()) + "</p>")
    for status in ORDER:
        rows = [it for it in items if it["status"] == status]
        parts.append(f"<h2>{html.escape(TITLES[status])} ({len(rows)})</h2>")
        if not rows:
            continue
        parts.append("<table><tr><th>Word</th><th>Aligned meaning</th><th>Alone (MT)</th><th>Dictionary</th>"
                     "<th>Sentence</th></tr>")
        for it in sorted(rows, key=lambda r: -r["count"]):
            s = by_id[it["sentence"]]
            sv = _sv_html(s["text"], [(t["text"], t["ws"]) for t in s["tokens"]], set(it["token_ids"]))
            times = f" &times;{it['count']}" if it["count"] > 1 else ""
            parts.append(
                f"<tr><td><b>{html.escape(it['words'])}</b>{times}<div class='small'>{html.escape(', '.join(it['lemmas']))}"
                f"</div></td><td>{html.escape(it['aligned'])}</td><td>{html.escape(', '.join(it['mt']))}</td>"
                f"<td>{html.escape(', '.join(it['dict']))}</td><td><div class='sv'>{sv}</div>"
                f"<div class='en'>{html.escape(it['en'])}</div>"
                f"<div class='small'>{html.escape(it['sentence'])}"
                f"{' &middot; also in ' + html.escape(', '.join(it['also_in'][:12])) if it['also_in'] else ''}"
                f"</div></td></tr>")
        parts.append("</table>")
    return "\n".join(parts)


def write_report(doc, out_dir=REVIEW_DIR):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    items = collect(doc)
    path = out_dir / f"{doc['id']}.html"
    path.write_text(render(doc, items), encoding="utf-8")
    (out_dir / f"{doc['id']}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return path, len(items)
