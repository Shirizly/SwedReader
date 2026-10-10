"""CLI: python -m pipeline run <url> [<url> ...] | publish | list | serve [port]"""
import sys

from . import db
from .assemble import build_document, slugify, write_document
from .config import ROOT, resolve_lane
from .publish import DATA, publish, serve
from .sources import fetch

DB_PATH = DATA / "private" / "pipeline.db"
_models = {}


def models():
    """Load spaCy and the translator once per process."""
    if not _models:
        import spacy
        from .translate import OpusMtTranslator
        _models["nlp"] = spacy.load("sv_core_news_sm")
        _models["translator"] = OpusMtTranslator()
        print(f"translator device: {_models['translator'].device}")
    return _models["nlp"], _models["translator"]


def run(url):
    lane_info = resolve_lane(url)  # lane is decided before anything is fetched or written
    lane = lane_info["lane"]
    print(f"\n{url}\nlane: {lane} ({lane_info['domain']})")
    conn = db.connect(_db_path())
    base = dict(id=slugify(url), source_url=url, source_domain=lane_info["domain"], lane=lane)
    try:
        source = fetch(url)
        print(f"fetched {source.title!r}: {sum(len(p) for _, p in source.sections)} paragraphs")
        lane_info = {**lane_info, "attribution": source.attribution or lane_info["attribution"]}
        nlp, translator = models()
        doc = build_document(url, lane_info, source.title, source.sections, nlp, translator, source.history_url)
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
    if cmd == "run" and len(argv) >= 2:
        failed = []
        for url in argv[1:]:
            try:
                run(url)
            except Exception as e:  # keep going; failures are logged in the database
                print(f"FAILED: {type(e).__name__}: {e}")
                failed.append(url)
        return 1 if failed else 0
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
