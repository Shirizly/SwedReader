import json
import sys
import types
import wave

import pytest

from pipeline.tts import (
    compress_wav_to_mp3,
    document_text,
    generate_aligned_audio,
    voice_asset_urls,
)


def test_document_text_keeps_sentence_order_and_limit(tmp_path):
    document = {
        "paragraphs": [
            {"sentences": [{"text": "Första meningen."}, {"text": "Andra meningen."}]},
            {"sentences": [{"text": "Tredje meningen."}]},
        ]
    }
    path = tmp_path / "story.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    assert document_text(path, sentence_limit=2) == "Första meningen.\nAndra meningen."
    assert document_text(path) == "Första meningen.\nAndra meningen.\nTredje meningen."


def test_document_text_requires_body_sentences(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text('{"paragraphs":[]}', encoding="utf-8")

    with pytest.raises(ValueError, match="body sentences"):
        document_text(path)


def test_voice_asset_urls_uses_voice_repository_layout():
    assert voice_asset_urls("sv_SE-alma-medium") == (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/sv/sv_SE/alma/medium/"
        "sv_SE-alma-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/sv/sv_SE/alma/medium/"
        "sv_SE-alma-medium.onnx.json",
    )


def test_voice_asset_urls_rejects_invalid_voice_names():
    with pytest.raises(ValueError, match="Unsupported Piper voice"):
        voice_asset_urls("../../untrusted-model")


def test_generate_aligned_audio_records_exact_sentence_boundaries(tmp_path, monkeypatch):
    class FakeVoice:
        @classmethod
        def load(cls, model_path):
            return cls()

        def synthesize_wav(self, text, wav_file):
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(10)
            wav_file.writeframes(b"\0\0" * 10)

    monkeypatch.setitem(sys.modules, "piper", types.SimpleNamespace(PiperVoice=FakeVoice))
    document_path = tmp_path / "story.json"
    document_path.write_text(json.dumps({
        "paragraphs": [{"sentences": [
            {"id": "s0", "text": "Första."},
            {"id": "s1", "text": "Andra."},
        ]}]
    }), encoding="utf-8")
    output_path = tmp_path / "story.wav"

    result = generate_aligned_audio(document_path, output_path, tmp_path / "voice.onnx")

    assert result["sentences"] == [
        {"id": "s0", "start": 0.0, "end": 1.0},
        {"id": "s1", "start": 1.1, "end": 2.1},
    ]
    assert result["total_sentences"] == 2
    with wave.open(str(output_path), "rb") as audio:
        assert audio.getframerate() == 10
        assert audio.getnframes() == 21


def test_compress_wav_to_mp3_creates_smaller_audio(tmp_path):
    wav_path = tmp_path / "source.wav"
    with wave.open(str(wav_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(22050)
        audio.writeframes(b"\0\0" * 22050)

    mp3_path = compress_wav_to_mp3(wav_path, tmp_path / "compressed.mp3")

    assert mp3_path.read_bytes()
    assert mp3_path.stat().st_size < wav_path.stat().st_size
