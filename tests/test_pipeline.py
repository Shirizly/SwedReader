import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

import jsonschema
import pytest
import spacy

from pipeline import db
from pipeline.assemble import build_document, slugify, validate, write_document
from pipeline.config import resolve_lane
from pipeline.publish import _make_handler, private_index, publish

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
    db.upsert_document(conn, **kw, word_count=10, output_path="reader/content/a.json")
    db.upsert_document(conn, **kw, status="failed", error="boom")
    rows = db.list_documents(conn)
    assert len(rows) == 1
    assert rows[0]["status"] == "failed" and rows[0]["word_count"] == 10  # earlier output info kept
    db.mark_published(conn, "a")
    assert db.list_documents(conn)[0]["published"] == 1


def test_publish_rebuilds_index_and_removes_stale_audio(nlp, tmp_path):
    content = tmp_path / "content"
    doc = make_doc(nlp)
    write_document(doc, content)
    (content / "index.json").write_text(json.dumps({"documents": []}), encoding="utf-8")
    stale_audio = content / "audio" / "stale.wav"
    stale_audio.parent.mkdir()
    stale_audio.write_bytes(b"old audio")
    assert publish(content) == ["sv-wikipedia-org-wiki-test"]
    assert not stale_audio.exists()
    index = json.loads((content / "index.json").read_text(encoding="utf-8"))
    assert [(d["id"], d["lane"]) for d in index["documents"]] == [(doc["id"], "public")]


def test_publish_indexes_valid_audio_asset_in_place(nlp, tmp_path):
    content_dir = tmp_path / "content"
    doc = make_doc(nlp)
    doc["audio"] = {
        "url": "content/audio/test.mp3",
        "sentences": [{"id": "s0", "start": 0, "end": 1}],
    }
    write_document(doc, content_dir)
    audio_path = content_dir / "audio" / "test.mp3"
    audio_path.parent.mkdir()
    audio_path.write_bytes(b"test wav")

    assert publish(content_dir) == [doc["id"]]
    assert (content_dir / "audio" / "test.mp3").read_bytes() == b"test wav"
    published_doc = json.loads((content_dir / f"{doc['id']}.json").read_text(encoding="utf-8"))
    assert published_doc["audio"]["url"] == "content/audio/test.mp3"


def test_reader_server_supports_byte_range_requests(tmp_path):
    asset_dir = tmp_path / "audio"
    asset_dir.mkdir()
    (asset_dir / "track.mp3").write_bytes(b"0123456789")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(tmp_path, tmp_path / "private"))
    thread = Thread(target=server.serve_forever)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port)
    try:
        connection.request("GET", "/audio/track.mp3", headers={"Range": "bytes=3-6"})
        response = connection.getresponse()
        assert response.status == 206
        assert response.getheader("Accept-Ranges") == "bytes"
        assert response.getheader("Content-Range") == "bytes 3-6/10"
        assert response.read() == b"3456"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("audio_url", ["https://example.org/audio.wav", "content/audio/../private.wav"])
def test_publish_rejects_unsafe_audio_url(nlp, tmp_path, audio_url):
    doc = make_doc(nlp)
    doc["audio"] = {"url": audio_url, "sentences": []}
    content_dir = tmp_path / "content"
    write_document(doc, content_dir)

    with pytest.raises(ValueError, match="invalid audio URL"):
        publish(content_dir)
    assert not (content_dir / "index.json").exists()


def test_publish_refuses_private_document_in_reader_content(nlp, tmp_path):
    priv_doc = make_doc(nlp, "https://www.svt.se/a")
    assert priv_doc["lane"] == "private"
    content_dir = tmp_path / "content"
    write_document(priv_doc, content_dir)
    with pytest.raises(ValueError):
        publish(content_dir)
    assert not (content_dir / "index.json").exists()


def test_private_index_lists_only_private(nlp, tmp_path):
    write_document(make_doc(nlp, "https://www.svt.se/a"), tmp_path)
    write_document(make_doc(nlp), tmp_path)
    idx = private_index(tmp_path)["documents"]
    assert [d["lane"] for d in idx] == ["private"]


def test_review_document_listing_skips_public_index(tmp_path, monkeypatch):
    from scripts import view_review

    public_dir, private_dir = tmp_path / "content", tmp_path / "private"
    public_dir.mkdir()
    private_dir.mkdir()
    (public_dir / "index.json").write_text(json.dumps({"documents": []}), encoding="utf-8")
    (public_dir / "public.json").write_text(json.dumps({"id": "public", "title": "Public"}), encoding="utf-8")
    (private_dir / "private.json").write_text(json.dumps({"id": "private", "title": "Private"}), encoding="utf-8")
    monkeypatch.setattr(view_review, "PUBLIC_CONTENT", public_dir)
    monkeypatch.setattr(view_review, "PRIVATE_DATA", private_dir)

    documents = view_review.documents()

    assert set(documents) == {"public", "private"}
    assert {lane for _, lane in documents.values()} == {"public", "private"}
