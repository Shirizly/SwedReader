#!/usr/bin/env python3
"""Generate and open a document's local HTML word-review report."""
import argparse
import json
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.review import REVIEW_DIR, write_report


def documents():
    found = {}
    for lane in ("public", "private"):
        for path in sorted((ROOT / "data" / lane).glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError(f"Could not read document {path}: {error}") from error
            found[data["id"]] = (data, lane)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_id", nargs="?", help="document ID, e.g. runeberg-org-kristleg-0113-html")
    parser.add_argument("--list", action="store_true", help="list available public and private documents")
    parser.add_argument("--no-open", action="store_true", help="generate the report without opening a browser")
    args = parser.parse_args()

    available = documents()
    if args.list or not args.document_id:
        if not available:
            print("No processed documents found under data/public or data/private.")
            return 0
        print("Available documents:")
        for doc_id, (document, lane) in sorted(available.items()):
            print(f"  {doc_id} ({lane}) — {document['title']}")
        if not args.list:
            print("\nRun this script with one of the document IDs to open its review report.")
        return 0

    item = available.get(args.document_id)
    if item:
        report_path, count = write_report(item[0])
        print(f"Generated {count} flagged review items.")
    else:
        report_path = REVIEW_DIR / f"{args.document_id}.html"
        if not report_path.is_file():
            parser.error(f"unknown document or review report: {args.document_id!r} (use --list)")

    print(f"Review report: {report_path}")
    if not args.no_open and not webbrowser.open(report_path.resolve().as_uri()):
        print("Could not open a browser automatically; open the report path above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
