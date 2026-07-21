"""Tests für services/voice_transcription.py — alle externen Calls gemockt."""

import sys
from dataclasses import fields
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

# Minimal OGG bytes (just enough to not be empty; duration will be mocked)
_FAKE_OGG = b"OggS" + b"\x00" * 200


# ---------------------------------------------------------------------------
# Test: TranscriptionResult dataclass fields
# ---------------------------------------------------------------------------


def test_transcription_result_fields():
    from services.voice_transcription import TranscriptionResult

    r = TranscriptionResult(
        text="Hallo",
        confidence=0.9,
        model_id="test-model",
        language_detected="de",
        duration_sec=5.0,
    )
    assert r.text == "Hallo"
    assert r.confidence == 0.9
    assert r.model_id == "test-model"
    assert r.language_detected == "de"
    assert r.duration_sec == 5.0

    field_names = {f.name for f in fields(TranscriptionResult)}
    assert field_names == {"text", "confidence", "model_id", "language_detected", "duration_sec"}


# ---------------------------------------------------------------------------
# Test: Gemini adapter success
# ---------------------------------------------------------------------------


def test_gemini_adapter_success():
    """transcribe_with_gemini läuft über den LiteLLM/Requesty-EU-HTTP-Proxy
    (nicht mehr das google.generativeai-SDK). Test entsprechend auf httpx-Mock
    umgestellt (2026-07-21)."""
    from services.voice_transcription import (
        _EU_VOICE_MODEL,
        TranscriptionResult,
        transcribe_with_gemini,
    )

    # OpenAI-Shape-Antwort des Routers (choices[0].message.content).
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "Das ist ein Test."}}]}

    mock_client = MagicMock()
    mock_client.__enter__.return_value.post.return_value = mock_resp

    mock_settings = MagicMock()
    mock_settings.litellm_base_url = "https://eu-router.example/v1"
    mock_settings.litellm_api_key = "fake-key"

    with patch("services.voice_transcription.httpx.Client", return_value=mock_client):
        with patch("config.settings", mock_settings):
            result = transcribe_with_gemini(_FAKE_OGG)

    assert isinstance(result, TranscriptionResult)
    assert result.text == "Das ist ein Test."
    assert result.confidence == 0.85
    assert result.model_id == _EU_VOICE_MODEL


# ---------------------------------------------------------------------------
# Test: Whisper not installed → TranscriptionError
# ---------------------------------------------------------------------------


def test_whisper_not_installed_raises():
    from services.voice_transcription import TranscriptionError, transcribe_with_whisper

    with patch.dict(sys.modules, {"faster_whisper": None}):
        # Ensure the import inside the function will raise ImportError
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "faster_whisper":
                raise ImportError("No module named 'faster_whisper'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(TranscriptionError, match="faster-whisper not installed"):
                transcribe_with_whisper(_FAKE_OGG)


# ---------------------------------------------------------------------------
# Test: Length limit enforced
# ---------------------------------------------------------------------------


def test_length_limit_enforced():
    from services.voice_transcription import TranscriptionError, transcribe_voice

    with patch("services.voice_transcription._get_ogg_duration", return_value=181.0):
        with pytest.raises(TranscriptionError, match="lang"):
            transcribe_voice(_FAKE_OGG)


# ---------------------------------------------------------------------------
# Test: Unknown MIME type rejected
# ---------------------------------------------------------------------------


def test_unknown_mime_type_rejected():
    from services.voice_transcription import TranscriptionError, transcribe_voice

    with pytest.raises(TranscriptionError, match="Unbekanntes Format"):
        transcribe_voice(_FAKE_OGG, mime_type="audio/mp3")


# ---------------------------------------------------------------------------
# Test: Fallback to Whisper on low Gemini confidence
# ---------------------------------------------------------------------------


def test_fallback_to_whisper_on_low_confidence():
    from services.voice_transcription import TranscriptionResult, transcribe_voice

    gemini_result = TranscriptionResult(
        text="unsicher",
        confidence=0.5,
        model_id="gemini-2.0-flash",
        language_detected="de",
        duration_sec=5.0,
    )
    whisper_result = TranscriptionResult(
        text="sicher transkribiert",
        confidence=0.9,
        model_id="faster-whisper-large-v3",
        language_detected="de",
        duration_sec=5.0,
    )

    with (
        patch("services.voice_transcription._get_ogg_duration", return_value=10.0),
        patch("services.voice_transcription.transcribe_with_gemini", return_value=gemini_result),
        patch(
            "services.voice_transcription.transcribe_with_whisper", return_value=whisper_result
        ) as mock_whisper,
    ):
        result = transcribe_voice(_FAKE_OGG)

    mock_whisper.assert_called_once()
    assert result.text == "sicher transkribiert"
    assert result.model_id == "faster-whisper-large-v3"


# ---------------------------------------------------------------------------
# Test: Fallback to Whisper when Gemini raises exception
# ---------------------------------------------------------------------------


def test_fallback_to_whisper_on_gemini_failure():
    from services.voice_transcription import (
        TranscriptionError,
        TranscriptionResult,
        transcribe_voice,
    )

    whisper_result = TranscriptionResult(
        text="Whisper hat es",
        confidence=0.8,
        model_id="faster-whisper-large-v3",
        language_detected="de",
        duration_sec=5.0,
    )

    with (
        patch("services.voice_transcription._get_ogg_duration", return_value=10.0),
        patch(
            "services.voice_transcription.transcribe_with_gemini",
            side_effect=TranscriptionError("Gemini down"),
        ),
        patch(
            "services.voice_transcription.transcribe_with_whisper", return_value=whisper_result
        ) as mock_whisper,
    ):
        result = transcribe_voice(_FAKE_OGG)

    mock_whisper.assert_called_once()
    assert result.text == "Whisper hat es"


# ---------------------------------------------------------------------------
# Test: Both providers fail → TranscriptionError("Alle")
# ---------------------------------------------------------------------------


def test_both_fail_raises():
    from services.voice_transcription import TranscriptionError, transcribe_voice

    with (
        patch("services.voice_transcription._get_ogg_duration", return_value=10.0),
        patch(
            "services.voice_transcription.transcribe_with_gemini",
            side_effect=TranscriptionError("Gemini down"),
        ),
        patch(
            "services.voice_transcription.transcribe_with_whisper",
            side_effect=TranscriptionError("Whisper down"),
        ),
        pytest.raises(TranscriptionError, match="Alle"),
    ):
        transcribe_voice(_FAKE_OGG)
