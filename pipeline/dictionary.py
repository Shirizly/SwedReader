"""Folkets lexikon (Swedish-English) as a local SQLite dictionary.

Source: https://folkets-lexikon.csc.kth.se/folkets/folkets_sv_en_public.xml
Licence: Creative Commons Attribution-Share Alike 2.5 (credit required; share-alike applies to the glosses).
"""
import html
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from .config import ROOT

XML_URL = "https://folkets-lexikon.csc.kth.se/folkets/folkets_sv_en_public.xml"
XML_PATH = ROOT / "data" / "private" / "folkets_sv_en_public.xml"
DB_PATH = ROOT / "data" / "private" / "dict.db"
INFO = {"name": "Folkets lexikon", "url": "https://folkets-lexikon.csc.kth.se/",
        "license": "CC-BY-SA-2.5", "license_url": "https://creativecommons.org/licenses/by-sa/2.5/"}
MAX_GLOSSES = 5

# spaCy universal POS -> Folkets word classes
POS_MAP = {"NOUN": ("nn",), "PROPN": ("pm", "nn"), "VERB": ("vb",), "AUX": ("vb",), "ADJ": ("jj",),
           "ADV": ("ab",), "ADP": ("pp",), "CCONJ": ("kn",), "SCONJ": ("sn", "kn"), "PRON": ("pn",),
           "DET": ("pn", "jj"), "NUM": ("rg",), "INTJ": ("in",)}

SCHEMA = """
DROP TABLE IF EXISTS entries; DROP TABLE IF EXISTS forms; DROP TABLE IF EXISTS meta;
CREATE TABLE entries (ord INTEGER, lemma TEXT, pos TEXT, gloss TEXT);
CREATE INDEX entries_lemma ON entries(lemma);
CREATE TABLE forms (form TEXT, lemma TEXT, pos TEXT);
CREATE INDEX forms_form ON forms(form);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


def _glosses(value):
    value = html.unescape(value).strip()
    parts = [value] if "(" in value else [p.strip() for p in value.split(",")]
    return [p for p in parts if p]


def build(xml_path=XML_PATH, db_path=DB_PATH):
    """(Re)build the SQLite dictionary from the Folkets XML. Returns the number of entries."""
    root = ET.parse(xml_path).getroot()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    rows, forms, n = [], [], 0
    for i, w in enumerate(root.iter("word")):
        lemma, pos = (w.get("value") or "").strip().lower(), w.get("class") or ""
        glosses = [g for t in w.findall("translation") for g in _glosses(t.get("value") or "")]
        if not lemma or not glosses:
            continue
        n += 1
        rows.extend((i, lemma, pos, g) for g in glosses)
        forms.extend((inf.get("value", "").strip().lower(), lemma, pos)
                     for inf in w.findall("paradigm/inflection") if inf.get("value"))
    conn.executemany("INSERT INTO entries VALUES (?,?,?,?)", rows)
    conn.executemany("INSERT INTO forms VALUES (?,?,?)", forms)
    conn.executemany("INSERT INTO meta VALUES (?,?)", [(k, v) for k, v in INFO.items()])
    conn.commit()
    conn.close()
    return n


class Dictionary:
    info = INFO

    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(str(db_path))

    def _rows(self, lemma):
        return self.conn.execute("SELECT pos, gloss FROM entries WHERE lemma = ? ORDER BY ord", (lemma,)).fetchall()

    def lookup(self, lemma, pos="", surface=""):
        """Up to MAX_GLOSSES English glosses for a lemma, preferring entries of the matching word class.
        Falls back to the lowercased surface form and to inflected forms listed in the dictionary."""
        wanted = POS_MAP.get(pos, ())
        for cand in dict.fromkeys(x.lower() for x in (lemma, surface) if x):
            rows = self._rows(cand)
            if not rows:
                for (base,) in self.conn.execute("SELECT DISTINCT lemma FROM forms WHERE form = ?", (cand,)):
                    rows = self._rows(base)
                    if rows:
                        break
            if rows:
                matching = [r for r in rows if r[0] in wanted]
                return list(dict.fromkeys(g for _, g in (matching or rows)))[:MAX_GLOSSES]
        return []
