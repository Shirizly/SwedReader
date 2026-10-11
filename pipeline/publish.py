"""Publish public documents to the reader and serve the reader locally (including private documents)."""
import json
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pathlib import PurePosixPath

from .config import PRIVATE_DATA, PUBLIC_CONTENT, READER

REQUIRED_PUBLIC = ("license", "license_url", "attribution")


def _index_entry(doc, path):
    return {"id": doc["id"], "title": doc["title"], "author": doc.get("author", ""), "path": path,
            "lane": doc["lane"], "word_count": doc["word_count"]}


def publish(content_dir=PUBLIC_CONTENT):
    """Validate public documents in the reader content directory and rebuild its index."""
    content_dir = Path(content_dir)
    content_dir.mkdir(parents=True, exist_ok=True)
    entries, ids, audio_assets = [], [], set()
    for src in sorted(content_dir.glob("*.json")):
        if src.name == "index.json":
            continue
        doc = json.loads(src.read_text(encoding="utf-8"))
        if doc.get("lane") != "public" or not all(doc.get(k) for k in REQUIRED_PUBLIC):
            raise ValueError(f"Refusing to publish {src.name}: not public or missing licence/attribution")
        audio = doc.get("audio")
        if audio:
            audio_url = audio.get("url", "")
            audio_path = PurePosixPath(audio_url)
            if (not audio_url.startswith("content/audio/")
                    or any(part in ("", ".", "..") for part in audio_path.parts)
                    or audio_path.suffix.lower() not in (".wav", ".mp3")):
                raise ValueError(f"Refusing to publish {src.name}: invalid audio URL")
            relative_audio_path = Path(*audio_path.parts[1:])
            audio_asset = content_dir / relative_audio_path
            if not audio_asset.is_file():
                raise ValueError(f"Refusing to publish {src.name}: audio asset missing at {audio_asset}")
            audio_assets.add(audio_asset)
        entries.append(_index_entry(doc, f"content/{src.name}"))
        ids.append(doc["id"])
    audio_dir = content_dir / "audio"
    if audio_dir.is_dir():
        for suffix in ("*.wav", "*.mp3"):
            for old_audio in audio_dir.rglob(suffix):
                if old_audio not in audio_assets:
                    old_audio.unlink()
    (content_dir / "index.json").write_text(
        json.dumps({"documents": entries}, ensure_ascii=False, indent=1), encoding="utf-8")
    return ids


def private_index(private_dir=PRIVATE_DATA):
    entries = []
    for p in sorted(Path(private_dir).glob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        if doc.get("lane") == "private":
            entries.append(_index_entry(doc, f"content-private/{p.name}"))
    return {"documents": entries}


def _make_handler(reader_dir, private_dir):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(reader_dir), **kw)

        def end_headers(self):
            if not self.path.startswith("/content-private/"):
                self.send_header("Accept-Ranges", "bytes")
            super().end_headers()

        def _serve_range(self):
            range_header = self.headers.get("Range", "")
            if not range_header.startswith("bytes=") or "," in range_header:
                return False
            path = Path(self.translate_path(self.path)).resolve()
            try:
                path.relative_to(reader_dir.resolve())
            except ValueError:
                return False
            if not path.is_file():
                return False
            size = path.stat().st_size
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
            if not match or size == 0:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return True
            first, last = match.groups()
            if not first:
                suffix_length = int(last or 0)
                if suffix_length == 0:
                    start = size
                else:
                    start = max(0, size - suffix_length)
                end = size - 1
            else:
                start = int(first)
                end = min(int(last) if last else size - 1, size - 1)
            if start >= size or end < start:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return True
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(str(path)))
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Last-Modified", self.date_time_string(path.stat().st_mtime))
            self.end_headers()
            with path.open("rb") as audio:
                audio.seek(start)
                self.wfile.write(audio.read(length))
            return True

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/content-private/index.json":
                body = json.dumps(private_index(private_dir), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path.startswith("/content-private/"):
                name = Path(path).name
                f = private_dir / name
                if not name.endswith(".json") or not f.is_file():
                    self.send_error(404)
                    return
                body = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                if not self._serve_range():
                    super().do_GET()

    return Handler


def serve(port=8765, reader_dir=READER, private_dir=PRIVATE_DATA):
    """Serve the reader with byte-range support and expose private docs locally."""
    reader_dir, private_dir = Path(reader_dir), Path(private_dir)

    server = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(reader_dir, private_dir))
    print(f"Reader at http://127.0.0.1:{port}/  (private documents included; Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
