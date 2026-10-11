import json
import shutil
from pathlib import Path

from pipeline.guard import check_reader_content

SOURCES = {"public": [{"domain": "wikipedia.org"}], "private": [{"domain": "svt.se"}]}
REAL_CONTENT = Path(__file__).resolve().parent.parent / "reader" / "content"


def doc(**kw):
    base = {"id": "a", "source_url": "https://sv.wikipedia.org/wiki/A", "lane": "public",
            "license": "CC-BY-SA-4.0", "license_url": "https://x", "attribution": "W"}
    return {**base, **kw}


def write(dir_, docs, index_lane="public"):
    dir_.mkdir(exist_ok=True)
    entries = []
    for d in docs:
        (dir_ / f"{d['id']}.json").write_text(json.dumps(d), encoding="utf-8")
        entries.append({"id": d["id"], "path": f"content/{d['id']}.json", "lane": index_lane})
    (dir_ / "index.json").write_text(json.dumps({"documents": entries}), encoding="utf-8")


def test_valid_public_content_passes(tmp_path):
    write(tmp_path / "c", [doc()])
    assert check_reader_content(tmp_path / "c", SOURCES) == []


def test_private_lane_document_fails(tmp_path):
    write(tmp_path / "c", [doc(lane="private")])
    assert any("not public" in p for p in check_reader_content(tmp_path / "c", SOURCES))


def test_private_source_mislabelled_as_public_fails(tmp_path):
    write(tmp_path / "c", [doc(source_url="https://www.svt.se/nyheter/x")])
    assert any("not a public-lane source" in p for p in check_reader_content(tmp_path / "c", SOURCES))


def test_missing_licence_fails(tmp_path):
    write(tmp_path / "c", [doc(license="")])
    assert any("missing license" in p for p in check_reader_content(tmp_path / "c", SOURCES))


def test_unlisted_and_stray_files_fail(tmp_path):
    write(tmp_path / "c", [doc()])
    (tmp_path / "c" / "extra.json").write_text(json.dumps(doc(id="extra")), encoding="utf-8")
    (tmp_path / "c" / "notes.txt").write_text("x", encoding="utf-8")
    problems = check_reader_content(tmp_path / "c", SOURCES)
    assert any("not listed" in p for p in problems) and any("unexpected file" in p for p in problems)


def test_referenced_wav_is_allowed_and_unreferenced_wav_is_rejected(tmp_path):
    content_dir = tmp_path / "c"
    write(content_dir, [doc(audio={
        "url": "content/audio/a.mp3",
        "sentences": [{"id": "s0", "start": 0, "end": 1}],
    })])
    audio_dir = content_dir / "audio"
    audio_dir.mkdir()
    (audio_dir / "a.mp3").write_bytes(b"audio")
    assert check_reader_content(content_dir, SOURCES) == []

    (audio_dir / "extra.mp3").write_bytes(b"audio")
    assert any("unreferenced audio" in problem for problem in check_reader_content(content_dir, SOURCES))


def test_committed_reader_content_is_publishable():
    assert check_reader_content(REAL_CONTENT) == []
