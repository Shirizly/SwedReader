"""Generate a local speech sample from a pipeline document."""
import argparse
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.tts import (
    DEFAULT_VOICE,
    compress_wav_to_mp3,
    download_voice,
    generate_aligned_audio,
    generate_audio,
)
from pipeline.config import PRIVATE_DATA, PUBLIC_CONTENT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", help="Path to a pipeline document JSON")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help=f"Piper voice (default: {DEFAULT_VOICE})")
    parser.add_argument("--sentences", type=int, help="Limit synthesis to the first N sentences")
    parser.add_argument("--output", type=Path, help="WAV destination (default: data/private/tts/samples/<document>.wav)")
    parser.add_argument("--attach", action="store_true",
                        help="Attach sentence-timed audio to a public document and publish it with pipeline publish")
    args = parser.parse_args()
    if args.sentences is not None and args.sentences < 1:
        parser.error("--sentences must be a positive integer")

    document_path = Path(args.document)
    if not document_path.is_absolute():
        document_path = ROOT / document_path
    model_dir = PRIVATE_DATA / "tts" / "voices"
    if args.attach:
        public_dir = PUBLIC_CONTENT.resolve()
        document_path = document_path.resolve()
        if not document_path.is_relative_to(public_dir):
            parser.error("--attach requires a public document from reader/content/")
        if args.output:
            parser.error("--output cannot be used with --attach")
        with document_path.open(encoding="utf-8") as document_file:
            document = json.load(document_file)
        if document.get("lane") != "public":
            parser.error("Only public-lane documents can carry published audio.")
        filename = f"{document['id']}_{args.voice}.mp3"
        output_path = public_dir / "audio" / filename
        previous_audio = document.get("audio", {})
        previous_url = previous_audio.get("url", "")
        previous_path = None
        if previous_url.startswith("content/audio/"):
            previous_parts = PurePosixPath(previous_url).parts
            previous_path = public_dir.joinpath(*previous_parts[1:])
        total_sentences = sum(
            1 for paragraph in document.get("paragraphs", [])
            for sentence in paragraph.get("sentences", [])
            if isinstance(sentence.get("text"), str) and sentence["text"].strip()
        )
        can_reuse_audio = (
            args.sentences is None
            and previous_audio.get("voice") == args.voice
            and len(previous_audio.get("sentences", [])) == total_sentences
            and previous_audio.get("total_sentences") == total_sentences
            and previous_path is not None
            and previous_path.suffix.lower() == ".wav"
            and previous_path.is_file()
        )
        old_wav_path = previous_path if can_reuse_audio else None
        if can_reuse_audio:
            alignment = {
                key: value for key, value in previous_audio.items()
                if key not in ("url", "voice")
            }
            compress_wav_to_mp3(previous_path, output_path)
        else:
            model_path = download_voice(args.voice, model_dir)
            staging_dir = PRIVATE_DATA / "tts" / "staging"
            staging_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=staging_dir) as temporary_dir:
                wav_path = Path(temporary_dir) / "track.wav"
                alignment = generate_aligned_audio(
                    document_path,
                    wav_path,
                    model_path,
                    sentence_limit=args.sentences,
                )
                compress_wav_to_mp3(wav_path, output_path)
        document["audio"] = {
            "url": f"content/audio/{filename}",
            "voice": args.voice,
            **alignment,
        }
        fd, temporary_path = tempfile.mkstemp(dir=document_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as document_file:
                json.dump(document, document_file, ensure_ascii=False, separators=(",", ":"))
            os.chmod(temporary_path, 0o644)
            os.replace(temporary_path, document_path)
        except BaseException:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
            raise
        if old_wav_path:
            old_wav_path.unlink()
        result = output_path
    else:
        output_path = args.output or PRIVATE_DATA / "tts" / "samples" / (
            f"{document_path.stem}_{args.voice}.wav"
        )
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        result = generate_audio(
            document_path,
            output_path,
            model_dir,
            voice=args.voice,
            sentence_limit=args.sentences if args.sentences is not None else 5,
        )
    print(f"Audio written to {result}")
    if args.attach:
        print(f"Sentence-timed audio attached to {document_path}; run `python -m pipeline publish` to rebuild the public index.")


if __name__ == "__main__":
    main()
