"""Guard: the published reader must contain only public-lane documents.

Run before deploying: python -m pipeline.guard
"""
import json
import sys
from pathlib import Path

from .config import ROOT, resolve_lane

REQUIRED = ("license", "license_url", "attribution")


def check_reader_content(content_dir=ROOT / "reader" / "content", sources=None):
    """Return a list of problems (empty if the content is safe to publish)."""
    content_dir = Path(content_dir)
    problems = []
    index_path = content_dir / "index.json"
    if not index_path.is_file():
        return [f"missing {index_path}"]
    listed = set()
    for entry in json.loads(index_path.read_text(encoding="utf-8")).get("documents", []):
        listed.add(Path(entry["path"]).name)
        if entry.get("lane") != "public":
            problems.append(f"index lists non-public document {entry.get('id')}")
    for f in sorted(content_dir.iterdir()):
        if f.name == "index.json":
            continue
        if f.suffix != ".json":
            problems.append(f"unexpected file in content: {f.name}")
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            problems.append(f"{f.name}: not valid JSON")
            continue
        if f.name not in listed:
            problems.append(f"{f.name}: not listed in index.json")
        if doc.get("lane") != "public":
            problems.append(f"{f.name}: lane is {doc.get('lane')!r}, not public")
        if resolve_lane(doc.get("source_url", ""), sources)["lane"] != "public":
            problems.append(f"{f.name}: source {doc.get('source_url')!r} is not a public-lane source")
        missing = [k for k in REQUIRED if not doc.get(k)]
        if missing:
            problems.append(f"{f.name}: missing {', '.join(missing)}")
    return problems


def main():
    problems = check_reader_content()
    for p in problems:
        print("ERROR:", p)
    print("content OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
