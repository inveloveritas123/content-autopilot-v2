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
    from services.voice_transcription import TranscriptionResult, transcribe_with_gemini

    mock_response = MagicMock()
    mock_response.text = "Das ist ein Test."

    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response

    mock_genai = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model

    mock_settings = MagicMock()
    mock_settings.gemini_api_key = "fake-key"

    with patch.dict(sys.modules, {"google.generativeai": mock_genai}):
        with patch("config.settings", mock_settings):
            result = transcribe_with_gemini(_FAKE_OGG)

    assert isinstance(result, TranscriptionResult)
    assert result.text == "Das ist ein Test."
    assert result.confidence == 0.85
    assert result.model_id == "gemini-2.0-flash"


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


# ---------------------------------------------------------------------------
# Test: Fehlerklassifikation — vorübergehend vs endgültig
# ---------------------------------------------------------------------------


def _http_error(status: int, body: str = "boom"):
    """Baut einen httpx.HTTPStatusError mit echtem Response-Objekt."""
    import httpx

    request = httpx.Request("POST", "https://router.example/v1/x")
    response = httpx.Response(status, text=body, request=request)
    return httpx.HTTPStatusError("err", request=request, response=response)


def test_429_is_transient():
    from services.voice_transcription import (
        TranscriptionUnavailable,
        _classify_http_error,
    )

    assert isinstance(_classify_http_error(_http_error(429)), TranscriptionUnavailable)


def test_503_is_transient():
    from services.voice_transcription import (
        TranscriptionUnavailable,
        _classify_http_error,
    )

    assert isinstance(_classify_http_error(_http_error(503)), TranscriptionUnavailable)


def test_403_is_terminal():
    from services.voice_transcription import (
        TranscriptionError,
        TranscriptionUnavailable,
        _classify_http_error,
    )

    err = _classify_http_error(_http_error(403, "not approved for this API key"))
    assert isinstance(err, TranscriptionError)
    assert not isinstance(err, TranscriptionUnavailable)
    # Der Body MUSS in der Meldung stehen — sonst ist ein 403 nicht von einem 400
    # zu unterscheiden und die Diagnose erfordert, den Call nachzubauen.
    assert "not approved" in str(err)


def test_retry_stops_after_three_attempts():
    from services.voice_transcription import TranscriptionUnavailable, _with_retry

    calls = []

    def _always_busy():
        calls.append(1)
        raise TranscriptionUnavailable("429")

    with patch("services.voice_transcription.time.sleep") as mock_sleep:
        with pytest.raises(TranscriptionUnavailable):
            _with_retry("test", _always_busy)

    assert len(calls) == 3
    # Zwischen drei Versuchen wird zweimal gewartet, mit 1s und 2s.
    assert [c.args[0] for c in mock_sleep.call_args_list] == [1, 2]


def test_retry_succeeds_on_second_attempt():
    from services.voice_transcription import TranscriptionUnavailable, _with_retry

    calls = []

    def _busy_once():
        calls.append(1)
        if len(calls) == 1:
            raise TranscriptionUnavailable("429")
        return "fertig"

    with patch("services.voice_transcription.time.sleep") as mock_sleep:
        assert _with_retry("test", _busy_once) == "fertig"

    assert len(calls) == 2
    assert mock_sleep.call_count == 1


def test_terminal_error_is_not_retried():
    from services.voice_transcription import TranscriptionError, _with_retry

    calls = []

    def _rejected():
        calls.append(1)
        raise TranscriptionError("403")

    with patch("services.voice_transcription.time.sleep") as mock_sleep:
        with pytest.raises(TranscriptionError):
            _with_retry("test", _rejected)

    assert len(calls) == 1
    assert mock_sleep.call_count == 0


# ---------------------------------------------------------------------------
# Test: kaputte 200er-Antwort — kein TranscriptionError, kein Retry, kein Silent-Escape
# ---------------------------------------------------------------------------


def _gemini_settings():
    mock_settings = MagicMock()
    mock_settings.litellm_base_url = "https://router.example/v1"
    mock_settings.litellm_api_key = "fake-key"
    return mock_settings


def test_gemini_non_json_200_is_terminal_error():
    import httpx

    from services.voice_transcription import (
        TranscriptionError,
        TranscriptionUnavailable,
        transcribe_with_gemini,
    )

    request = httpx.Request("POST", "https://router.example/v1/chat/completions")
    response = httpx.Response(200, text="<html>502 Bad Gateway</html>", request=request)

    with (
        patch("config.settings", _gemini_settings()),
        patch("services.voice_transcription.time.sleep"),
        patch("httpx.Client") as mock_client_cls,
    ):
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.post.return_value = response

        with pytest.raises(TranscriptionError) as exc_info:
            transcribe_with_gemini(_FAKE_OGG)

    assert not isinstance(exc_info.value, TranscriptionUnavailable)
    assert instance.post.call_count == 1
    assert "Unerwartete Router-Antwort" in str(exc_info.value)


def test_gemini_malformed_choices_is_terminal_error():
    import httpx

    from services.voice_transcription import (
        TranscriptionError,
        TranscriptionUnavailable,
        transcribe_with_gemini,
    )

    request = httpx.Request("POST", "https://router.example/v1/chat/completions")
    response = httpx.Response(200, json={"choices": ["kein dict"]}, request=request)

    with (
        patch("config.settings", _gemini_settings()),
        patch("services.voice_transcription.time.sleep"),
        patch("httpx.Client") as mock_client_cls,
    ):
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.post.return_value = response

        with pytest.raises(TranscriptionError) as exc_info:
            transcribe_with_gemini(_FAKE_OGG)

    assert not isinstance(exc_info.value, TranscriptionUnavailable)
    assert instance.post.call_count == 1
    assert "Unerwartete Router-Antwort" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test: Router-Fehler ausserhalb von httpx bleiben TranscriptionError
# (Fix-Runde 2 — der wiederhergestellte Catch-all)
# ---------------------------------------------------------------------------


def test_invalid_base_url_is_a_terminal_transcription_error():
    """Eine kaputte LITELLM_BASE_URL wirft httpx.InvalidURL — weder eine
    httpx.RequestError-Unterklasse noch eine der in Fix-Runde 1 gefangenen
    (ValueError/TypeError/KeyError/IndexError/AttributeError). Ohne den in dieser
    Runde wiederhergestellten Catch-all entkommt das als roher httpx.InvalidURL statt
    TranscriptionError — genau der Silent-Escape-Pfad, den dieser Befund beschreibt.
    """
    from services.voice_transcription import (
        TranscriptionError,
        TranscriptionUnavailable,
        transcribe_with_gemini,
    )

    mock_settings = MagicMock()
    mock_settings.litellm_base_url = "https://[::1"  # ungueltiger Port -> httpx.InvalidURL
    mock_settings.litellm_api_key = "fake-key"

    with (
        patch("config.settings", mock_settings),
        patch("services.voice_transcription.time.sleep"),
    ):
        with pytest.raises(TranscriptionError) as exc_info:
            transcribe_with_gemini(_FAKE_OGG)

    assert not isinstance(exc_info.value, TranscriptionUnavailable)
    assert "Router-Fehler" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test: Voxtral-Adapter
# ---------------------------------------------------------------------------


def _voxtral_settings():
    s = MagicMock()
    s.litellm_base_url = "https://router.example/v1"
    s.litellm_api_key = "fake-key"
    return s


def test_voxtral_parses_json_text():
    """Der Router liefert JSON — auch bei response_format=text (live gemessen 03.08.)."""
    import httpx

    from services.voice_transcription import TranscriptionResult, transcribe_with_voxtral

    request = httpx.Request("POST", "https://router.example/v1/audio/transcriptions")
    response = httpx.Response(
        200,
        json={"text": "Das ist ein Test.", "usage": {"type": "duration", "seconds": 3}},
        request=request,
    )

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = response

    with patch("config.settings", _voxtral_settings()):
        with patch("services.voice_transcription.httpx.Client", return_value=mock_client):
            with patch("services.voice_transcription._get_ogg_duration", return_value=3.0):
                result = transcribe_with_voxtral(_FAKE_OGG)

    assert isinstance(result, TranscriptionResult)
    assert result.text == "Das ist ein Test."
    assert result.model_id == "mistral/voxtral-mini-latest"
    assert result.confidence == 1.0

    # Multipart-Form, nicht JSON-Body — und die Modell-ID mit Provider-Prefix.
    _, kwargs = mock_client.post.call_args
    assert kwargs["data"]["model"] == "mistral/voxtral-mini-latest"
    assert "file" in kwargs["files"]


def test_voxtral_403_is_terminal_and_not_retried():
    import httpx

    from services.voice_transcription import (
        TranscriptionError,
        TranscriptionUnavailable,
        transcribe_with_voxtral,
    )

    request = httpx.Request("POST", "https://router.example/v1/audio/transcriptions")
    response = httpx.Response(403, text="not approved for this API key", request=request)

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = response

    with patch("config.settings", _voxtral_settings()):
        with patch("services.voice_transcription.httpx.Client", return_value=mock_client):
            with patch("services.voice_transcription.time.sleep") as mock_sleep:
                with pytest.raises(TranscriptionError) as excinfo:
                    transcribe_with_voxtral(_FAKE_OGG)

    assert not isinstance(excinfo.value, TranscriptionUnavailable)
    assert mock_client.post.call_count == 1
    assert mock_sleep.call_count == 0


def test_voxtral_429_is_retried_then_succeeds():
    import httpx

    from services.voice_transcription import transcribe_with_voxtral

    request = httpx.Request("POST", "https://router.example/v1/audio/transcriptions")
    busy = httpx.Response(429, text="rate limited", request=request)
    ok = httpx.Response(200, json={"text": "Endlich."}, request=request)

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.side_effect = [busy, ok]

    with patch("config.settings", _voxtral_settings()):
        with patch("services.voice_transcription.httpx.Client", return_value=mock_client):
            with patch("services.voice_transcription._get_ogg_duration", return_value=2.0):
                with patch("services.voice_transcription.time.sleep") as mock_sleep:
                    result = transcribe_with_voxtral(_FAKE_OGG)

    assert result.text == "Endlich."
    assert mock_client.post.call_count == 2
    assert mock_sleep.call_count == 1


def test_voxtral_empty_text_is_terminal():
    import httpx

    from services.voice_transcription import (
        TranscriptionError,
        TranscriptionUnavailable,
        transcribe_with_voxtral,
    )

    request = httpx.Request("POST", "https://router.example/v1/audio/transcriptions")
    response = httpx.Response(200, json={"text": "   "}, request=request)

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = response

    with patch("config.settings", _voxtral_settings()):
        with patch("services.voice_transcription.httpx.Client", return_value=mock_client):
            with pytest.raises(TranscriptionError) as excinfo:
                transcribe_with_voxtral(_FAKE_OGG)

    assert not isinstance(excinfo.value, TranscriptionUnavailable)


def test_voxtral_invalid_base_url_is_terminal():
    """httpx.InvalidURL erbt direkt von Exception, nicht von httpx.RequestError — eine
    kaputte LITELLM_BASE_URL entkommt ohne einen Catch-all-Zweig in _call() roh an
    TranscriptionError vorbei. Kein httpx.Client-Mock: der Fehler muss aus echtem
    httpx kommen, sonst testet das nur den eigenen Mock.
    """
    from services.voice_transcription import (
        TranscriptionError,
        TranscriptionUnavailable,
        transcribe_with_voxtral,
    )

    mock_settings = MagicMock()
    mock_settings.litellm_base_url = "https://[::1"  # ungueltiger Port -> httpx.InvalidURL
    mock_settings.litellm_api_key = "fake-key"

    with (
        patch("config.settings", mock_settings),
        patch("services.voice_transcription.time.sleep"),
    ):
        with pytest.raises(TranscriptionError) as excinfo:
            transcribe_with_voxtral(_FAKE_OGG)

    assert not isinstance(excinfo.value, TranscriptionUnavailable)
    assert "Router-Fehler" in str(excinfo.value)
