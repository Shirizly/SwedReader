"""CLI: python -m pipeline run <url> | publish | list | serve [port]"""
import sys
from pathlib import Path
from urllib.parse import urlparse

from . import db
from .assemble import build_document, slugify, write_document
from .config import ROOT, resolve_lane
from .fetch import fetch
from .publish import DATA, publish, serve

DB_PATH = DATA / "private" / "pipeline.db"


def history_url_for(url, title):
    p = urlparse(url)
    if p.hostname and p.hostname.endswith("wikipedia.org"):
        return f"{p.scheme}://{p.netloc}/w/index.php?title={title.replace(' ', '_')}&action=history"
    return ""


def run(url):
    lane_info = resolve_lane(url)  # lane is decided before anything is fetched or written
    lane = lane_info["lane"]
    print(f"lane: {lane} ({lane_info['domain']})")
    conn = db.connect(_db_path())
    base = dict(id=slugify(url), source_url=url, source_domain=lane_info["domain"], lane=lane)
    try:
        title, sections = fetch(url)
        print(f"fetched {title!r}: {sum(len(p) for _, p in sections)} paragraphs")
        import spacy
        from .translate import OpusMtTranslator
        nlp = spacy.load("sv_core_news_sm")
        translator = OpusMtTranslator()
        doc = build_document(url, lane_info, title, sections, nlp, translator, history_url_for(url, title))
        path, digest = write_document(doc, DATA / lane)
    except Exception as e:
        db.upsert_document(conn, **base, status="failed", error=f"{type(e).__name__}: {e}")
        raise
    db.upsert_document(conn, **base, word_count=doc["word_count"],
                       output_path=str(path.relative_to(ROOT)), content_hash=digest)
    print(f"wrote {path.relative_to(ROOT)} ({doc['word_count']} words)")
    return path


def _db_path():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "run" and len(argv) == 2:
        run(argv[1])
    elif cmd == "publish":
        ids = publish()
        conn = db.connect(_db_path())
        for i in ids:
            db.mark_published(conn, i)
        print("published:", ", ".join(ids) or "(none)")
    elif cmd == "list":
        for r in db.list_documents(db.connect(_db_path())):
            print(f"{r['loaded_at']}  {r['lane']:<7} {r['status']:<6} {r['word_count'] or '-':>6} words  "
                  f"pub={r['published']}  {r['source_url']}")
    elif cmd == "serve":
        serve(int(argv[1]) if len(argv) > 1 else 8765)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
