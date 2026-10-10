"""Publish public documents to the reader and serve the reader locally (including private documents)."""
import json
import shutil
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import ROOT

DATA = ROOT / "data"
READER = ROOT / "reader"
REQUIRED_PUBLIC = ("license", "license_url", "attribution")


def _index_entry(doc, path):
    return {"id": doc["id"], "title": doc["title"], "path": path, "lane": doc["lane"],
            "word_count": doc["word_count"]}


def publish(public_dir=DATA / "public", content_dir=READER / "content"):
    """Copy valid public documents into the reader and rebuild its index. Returns published ids."""
    public_dir, content_dir = Path(public_dir), Path(content_dir)
    content_dir.mkdir(parents=True, exist_ok=True)
    entries, ids = [], []
    for src in sorted(public_dir.glob("*.json")):
        doc = json.loads(src.read_text(encoding="utf-8"))
        if doc.get("lane") != "public" or not all(doc.get(k) for k in REQUIRED_PUBLIC):
            raise ValueError(f"Refusing to publish {src.name}: not public or missing licence/attribution")
        shutil.copyfile(src, content_dir / src.name)
        entries.append(_index_entry(doc, f"content/{src.name}"))
        ids.append(doc["id"])
    # Remove previously published documents that are no longer in data/public.
    for old in content_dir.glob("*.json"):
        if old.name != "index.json" and old.stem not in ids:
            old.unlink()
    (content_dir / "index.json").write_text(
        json.dumps({"documents": entries}, ensure_ascii=False, indent=1), encoding="utf-8")
    return ids


def private_index(private_dir=DATA / "private"):
    entries = []
    for p in sorted(Path(private_dir).glob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        if doc.get("lane") == "private":
            entries.append(_index_entry(doc, f"content-private/{p.name}"))
    return {"documents": entries}


def serve(port=8765, reader_dir=READER, private_dir=DATA / "private"):
    """Serve the unmodified reader plus data/private at /content-private/ (local only)."""
    reader_dir, private_dir = Path(reader_dir), Path(private_dir)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(reader_dir), **kw)

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
                super().do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Reader at http://127.0.0.1:{port}/  (private documents included; Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
