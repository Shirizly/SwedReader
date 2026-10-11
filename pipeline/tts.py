"""Local Swedish speech synthesis for testing Piper voices against project documents."""
import json
import io
import os
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import requests

DEFAULT_VOICE = "sv_SE-alma-medium"
VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
VOICE_TIMEOUT = (10, 120)


def voice_asset_urls(voice):
    """Return the model and config URLs for a voice hosted in the Piper voice repository."""
    match = re.fullmatch(r"([a-z]{2}_[A-Z]{2})-([a-z0-9]+)-([a-z]+)", voice)
    if not match:
        raise ValueError(f"Unsupported Piper voice name: {voice!r}")
    locale, speaker, quality = match.groups()
    relative_path = f"{locale[:2]}/{locale}/{speaker}/{quality}/{voice}"
    base = f"{VOICE_BASE_URL}/{relative_path}"
    return base + ".onnx", base + ".onnx.json"


def document_text(document_path, sentence_limit=None):
    """Read body sentences from a pipeline document, preserving sentence boundaries."""
    path = Path(document_path)
    with path.open(encoding="utf-8") as document_file:
        document = json.load(document_file)
    paragraphs = document.get("paragraphs")
    if not isinstance(paragraphs, list):
        raise ValueError(f"{path} does not contain a paragraphs list")

    sentences = []
    for paragraph in paragraphs:
        for sentence in paragraph.get("sentences", []):
            text = sentence.get("text")
            if isinstance(text, str) and text.strip():
                sentences.append(text.strip())
                if sentence_limit is not None and len(sentences) >= sentence_limit:
                    return "\n".join(sentences)
    if not sentences:
        raise ValueError(f"{path} does not contain any body sentences")
    return "\n".join(sentences)


def download_voice(voice, model_dir):
    """Download the selected model and its configuration into a local private cache."""
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / f"{voice}.onnx"
    config_path = model_dir / f"{voice}.onnx.json"
    if model_path.is_file() and config_path.is_file():
        return model_path

    for url, destination in zip(voice_asset_urls(voice), (model_path, config_path)):
        if destination.is_file():
            continue
        fd, temporary_path = tempfile.mkstemp(dir=model_dir, suffix=".download")
        try:
            with os.fdopen(fd, "wb") as output_file:
                with requests.get(url, stream=True, timeout=VOICE_TIMEOUT) as response:
                    response.raise_for_status()
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output_file.write(chunk)
            os.replace(temporary_path, destination)
        except BaseException:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
            raise
    return model_path


def synthesize(text, model_path, output_path):
    """Run Piper safely and replace the output only after successful synthesis."""
    executable = shutil.which("piper")
    if executable is None:
        raise RuntimeError("Piper executable not found; install project requirements in translatepipe.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.stem}-",
        suffix=".wav",
    )
    os.close(fd)
    os.unlink(temporary_path)
    try:
        subprocess.run(
            [executable, "--model", str(model_path), "--output_file", temporary_path],
            input=text,
            text=True,
            check=True,
        )
        if not Path(temporary_path).is_file() or Path(temporary_path).stat().st_size == 0:
            raise RuntimeError("Piper completed without producing a non-empty audio file.")
        os.replace(temporary_path, output_path)
    except BaseException:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise
    return output_path


def generate_audio(document_path, output_path, model_dir, voice=DEFAULT_VOICE, sentence_limit=None):
    """Generate a local WAV sample from the first body sentences of a pipeline document."""
    text = document_text(document_path, sentence_limit)
    model_path = download_voice(voice, model_dir)
    return synthesize(text, model_path, output_path)


def generate_aligned_audio(document_path, output_path, model_path, sentence_limit=None, progress=print):
    """Synthesize sentence-by-sentence and return exact sentence boundaries in the combined WAV."""
    from piper import PiperVoice

    document_path = Path(document_path)
    with document_path.open(encoding="utf-8") as document_file:
        document = json.load(document_file)
    sentences = [
        sentence
        for paragraph in document.get("paragraphs", [])
        for sentence in paragraph.get("sentences", [])
        if isinstance(sentence.get("text"), str) and sentence["text"].strip()
    ]
    if sentence_limit is not None:
        sentences = sentences[:sentence_limit]
    if not sentences:
        raise ValueError(f"{document_path} does not contain any body sentences")

    voice = PiperVoice.load(model_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.stem}-",
        suffix=".wav",
    )
    os.close(fd)
    os.unlink(temporary_path)

    boundaries = []
    frame_position = 0
    audio_params = None
    try:
        with wave.open(temporary_path, "wb") as combined:
            for index, sentence in enumerate(sentences):
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as sentence_file:
                    voice.synthesize_wav(sentence["text"].strip(), sentence_file)
                with wave.open(io.BytesIO(buffer.getvalue()), "rb") as sentence_audio:
                    params = sentence_audio.getparams()
                    if audio_params is None:
                        audio_params = params
                        combined.setparams(params)
                    elif (params.nchannels, params.sampwidth, params.framerate) != (
                        audio_params.nchannels, audio_params.sampwidth, audio_params.framerate
                    ):
                        raise RuntimeError("Piper changed audio format between sentences.")

                    start = frame_position / params.framerate
                    frames = sentence_audio.readframes(params.nframes)
                    combined.writeframesraw(frames)
                    frame_position += params.nframes
                    end = frame_position / params.framerate
                    boundaries.append({"id": sentence["id"], "start": start, "end": end})

                    if index + 1 < len(sentences):
                        silence_frames = round(params.framerate * 0.12)
                        combined.writeframesraw(b"\0" * silence_frames * params.nchannels * params.sampwidth)
                        frame_position += silence_frames
                if (index + 1) % 50 == 0:
                    progress(f"{document_path.stem}: synthesized {index + 1}/{len(sentences)} sentences")
        if not Path(temporary_path).is_file() or Path(temporary_path).stat().st_size == 0:
            raise RuntimeError("Piper completed without producing a non-empty audio file.")
        os.replace(temporary_path, output_path)
    except BaseException:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise

    return {
        "sentences": boundaries,
        "total_sentences": sum(
            1 for paragraph in document.get("paragraphs", [])
            for sentence in paragraph.get("sentences", [])
            if isinstance(sentence.get("text"), str) and sentence["text"].strip()
        ),
        "duration": frame_position / audio_params.framerate,
    }


def compress_wav_to_mp3(wav_path, output_path, bitrate=64):
    """Encode a mono WAV to a compact MP3 file, replacing the destination atomically."""
    import lameenc

    wav_path, output_path = Path(wav_path), Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.stem}-",
        suffix=".mp3",
    )
    try:
        encoder = lameenc.Encoder()
        with wave.open(str(wav_path), "rb") as source, os.fdopen(fd, "wb") as destination:
            if source.getsampwidth() != 2:
                raise ValueError("MP3 encoding requires 16-bit PCM input.")
            encoder.set_in_sample_rate(source.getframerate())
            encoder.set_channels(source.getnchannels())
            encoder.set_bit_rate(bitrate)
            encoder.set_quality(2)
            while frames := source.readframes(8192):
                destination.write(encoder.encode(frames))
            destination.write(encoder.flush())
        if not Path(temporary_path).is_file() or Path(temporary_path).stat().st_size == 0:
            raise RuntimeError("MP3 encoding completed without producing a non-empty file.")
        os.replace(temporary_path, output_path)
    except BaseException:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise
    return output_path
