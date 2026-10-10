import json

import jsonschema
import pytest
import spacy

from pipeline import db
from pipeline.assemble import build_document, slugify, validate, write_document
from pipeline.config import resolve_lane
from pipeline.publish import private_index, publish

SOURCES = {
    "public": [{"domain": "wikipedia.org", "license": "CC-BY-SA-4.0", "license_url": "https://x/l",
                "attribution": "Wikipedia"}],
    "private": [{"domain": "svt.se"}],
}


class FakeTranslator:
    name = "fake"

    def translate(self, sentences):
        return [f"EN: {s}" for s in sentences]

    def translate_words(self, words):
        return [f"{w}-en" for w in words]

    def align(self, src_text, tokens, tgt_text):
        return [t["text"].lower() if t["is_word"] else "" for t in tokens], []


@pytest.fixture(scope="module")
def nlp():
    return spacy.blank("sv")


def make_doc(nlp, url="https://sv.wikipedia.org/wiki/Test", sources=SOURCES):
    lane = resolve_lane(url, sources)
    sections = [(None, ["Första meningen. Andra meningen."]), ("Rubrik", ["Tredje."])]
    return build_document(url, lane, "Test", sections, nlp, FakeTranslator(), progress=lambda *_: None)


@pytest.mark.parametrize("url,lane", [
    ("https://sv.wikipedia.org/wiki/Stockholm", "public"),
    ("https://www.svt.se/nyheter/x", "private"),
    ("https://8sidor.se/a", "private"),
    ("https://notsvt.se/a", "private"),
    ("https://svt.se.evil.com/a", "private"),
    ("https://unknown.example/a", "private"),
])
def test_lane_resolution(url, lane):
    assert resolve_lane(url, SOURCES)["lane"] == lane


def test_invalid_url_rejected():
    with pytest.raises(ValueError):
        resolve_lane("not a url", SOURCES)


def test_build_document_structure_and_word_count(nlp):
    doc = make_doc(nlp)
    validate(doc)
    sents = [s for p in doc["paragraphs"] for s in p["sentences"]]
    assert [s["text"] for s in sents] == ["Första meningen.", "Andra meningen.", "Tredje."]
    assert doc["paragraphs"][1]["heading"] == "Rubrik"
    assert doc["word_count"] == 5
    assert sents[0]["tokens"][0]["in_context"] == "första"
    assert "in_context" not in sents[0]["tokens"][-1]  # punctuation has none


def test_public_document_requires_licence(nlp):
    doc = make_doc(nlp)
    doc["license"] = ""
    with pytest.raises(jsonschema.ValidationError):
        validate(doc)


def test_write_document_is_atomic_and_deterministic(nlp, tmp_path):
    doc = make_doc(nlp)
    p1, h1 = write_document(doc, tmp_path)
    p2, h2 = write_document(doc, tmp_path)
    assert p1 == p2 and h1 == h2
    assert not list(tmp_path.glob("*.tmp"))
    bad = dict(doc, word_count="x")
    with pytest.raises(jsonschema.ValidationError):
        write_document(bad, tmp_path)
    assert json.loads(p1.read_text(encoding="utf-8"))["id"] == doc["id"]  # earlier output intact


def test_slugify():
    assert slugify("https://sv.wikipedia.org/wiki/Stockholm") == "sv-wikipedia-org-wiki-stockholm"


def test_db_upsert_does_not_duplicate(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    kw = dict(id="a", source_url="https://x/a", source_domain="x", lane="public")
    db.upsert_document(conn, **kw, word_count=10, output_path="data/public/a.json")
    db.upsert_document(conn, **kw, status="failed", error="boom")
    rows = db.list_documents(conn)
    assert len(rows) == 1
    assert rows[0]["status"] == "failed" and rows[0]["word_count"] == 10  # earlier output info kept
    db.mark_published(conn, "a")
    assert db.list_documents(conn)[0]["published"] == 1


def test_publish_copies_only_public_and_rebuilds_index(nlp, tmp_path):
    pub, content = tmp_path / "public", tmp_path / "content"
    write_document(make_doc(nlp), pub)
    content.mkdir()
    (content / "stale.json").write_text("{}")
    assert publish(pub, content) == ["sv-wikipedia-org-wiki-test"]
    assert not (content / "stale.json").exists()
    index = json.loads((content / "index.json").read_text(encoding="utf-8"))
    assert [d["lane"] for d in index["documents"]] == ["public"]


def test_publish_refuses_private_document_in_public_dir(nlp, tmp_path):
    priv_doc = make_doc(nlp, "https://www.svt.se/a")
    assert priv_doc["lane"] == "private"
    pub = tmp_path / "public"
    write_document(priv_doc, pub)
    with pytest.raises(ValueError):
        publish(pub, tmp_path / "content")
    assert not (tmp_path / "content" / "svt-se-a.json").exists()


def test_private_index_lists_only_private(nlp, tmp_path):
    write_document(make_doc(nlp, "https://www.svt.se/a"), tmp_path)
    write_document(make_doc(nlp), tmp_path)
    idx = private_index(tmp_path)["documents"]
    assert [d["lane"] for d in idx] == ["private"]
