"""Guard: the published reader must contain only public-lane documents.

Run before deploying: python -m pipeline.guard
"""
import json
import sys
from pathlib import Path
from pathlib import PurePosixPath

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
    referenced_audio = set()
    for entry in json.loads(index_path.read_text(encoding="utf-8")).get("documents", []):
        listed.add(Path(entry["path"]).name)
        if entry.get("lane") != "public":
            problems.append(f"index lists non-public document {entry.get('id')}")
    for f in sorted(content_dir.iterdir()):
        if f.name == "index.json":
            continue
        if f.is_dir() and f.name == "audio":
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
        audio = doc.get("audio")
        if audio:
            url = audio.get("url", "")
            audio_path = PurePosixPath(url)
            if (not url.startswith("content/audio/")
                    or any(part in ("", ".", "..") for part in audio_path.parts)
                    or audio_path.suffix.lower() not in (".wav", ".mp3")):
                problems.append(f"{f.name}: invalid audio URL")
            else:
                asset = content_dir.joinpath(*audio_path.parts[1:])
                referenced_audio.add(asset)
                if not asset.is_file():
                    problems.append(f"{f.name}: missing audio asset {audio_path}")
    audio_dir = content_dir / "audio"
    if audio_dir.exists():
        for audio_file in audio_dir.rglob("*"):
            if not audio_file.is_file() or audio_file.suffix.lower() not in (".wav", ".mp3"):
                problems.append(f"unexpected file in content: {audio_file.relative_to(content_dir)}")
            elif audio_file not in referenced_audio:
                problems.append(f"unreferenced audio in content: {audio_file.relative_to(content_dir)}")
    return problems


def main():
    problems = check_reader_content()
    for p in problems:
        print("ERROR:", p)
    print("content OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
