"""CLI: python -m pipeline run <url> [<url> ...] | publish | list | serve [port] | build-dict | review <doc-id>"""
import json
import sys

from . import db
from .assemble import build_document, slugify, write_document
from .config import PRIVATE_DATA, PUBLIC_CONTENT, ROOT, resolve_lane
from .publish import publish, serve
from .sources import fetch

DB_PATH = PRIVATE_DATA / "pipeline.db"
_models = {}


def models():
    """Load spaCy, the translator, the dictionary (if built) and an English lemmatizer once per process."""
    if not _models:
        import functools

        import spacy
        from . import dictionary
        from .translate import OpusMtTranslator
        _models["nlp"] = spacy.load("sv_core_news_sm")
        _models["translator"] = OpusMtTranslator()
        print(f"translator device: {_models['translator'].device}")
        _models["dictionary"] = dictionary.Dictionary() if dictionary.DB_PATH.exists() else None
        if _models["dictionary"] is None:
            print("note: no dictionary found (run: python -m pipeline build-dict); using machine translation only")
        en = spacy.load("en_core_web_sm", disable=["parser", "ner"])

        @functools.lru_cache(maxsize=None)
        def lemmas(text):
            return tuple(t.lemma_.lower() for t in en(text) if t.is_alpha)

        _models["lemmas"] = lemmas
    return _models["nlp"], _models["translator"], _models["dictionary"], _models["lemmas"]


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
        nlp, translator, dictionary, lemmas = models()
        doc = build_document(url, lane_info, source.title, source.sections, nlp, translator, source.history_url,
                             author=source.author, dictionary=dictionary, lemmas=lemmas)
        destination = PUBLIC_CONTENT if lane == "public" else PRIVATE_DATA
        path, digest = write_document(doc, destination)
    except Exception as e:
        db.upsert_document(conn, **base, status="failed", error=f"{type(e).__name__}: {e}")
        raise
    db.upsert_document(conn, **base, word_count=doc["word_count"],
                       output_path=str(path.relative_to(ROOT)), content_hash=digest)
    print(f"wrote {path.relative_to(ROOT)} ({doc['word_count']} words); QA: {doc.get('qa')}")
    from .review import write_report
    report, n = write_report(doc)
    print(f"review report: {report.relative_to(ROOT)} ({n} flagged)")
    return path


def _db_path():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def build_dictionary():
    from . import dictionary
    if not dictionary.XML_PATH.exists():
        from .sources.base import PoliteFetcher
        print("downloading", dictionary.XML_URL)
        dictionary.XML_PATH.parent.mkdir(parents=True, exist_ok=True)
        dictionary.XML_PATH.write_bytes(PoliteFetcher().get_bytes(dictionary.XML_URL))
    n = dictionary.build()
    print(f"built {dictionary.DB_PATH.relative_to(ROOT)}: {n} entries")


def review(doc_id):
    from .review import write_report
    for lane in ("public", "private"):
        directory = PUBLIC_CONTENT if lane == "public" else PRIVATE_DATA
        path = directory / f"{doc_id}.json"
        if path.exists():
            report, n = write_report(json.loads(path.read_text(encoding="utf-8")))
            print(f"review report: {report.relative_to(ROOT)} ({n} flagged)")
            return 0
    print(f"no document {doc_id!r} in reader/content or data/private")
    return 1


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
    elif cmd == "build-dict":
        build_dictionary()
    elif cmd == "review" and len(argv) == 2:
        return review(argv[1])
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
