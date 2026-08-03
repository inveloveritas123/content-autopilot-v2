"""Fehlerpfade des Voice-Handlings — alles gemockt.

Hintergrund: Am 03.08.2026 ging eine Sprachnachricht verloren, weil _process_voice
im gesamten Fehlerpfad kein _send_telegram_message kannte. Diese Tests halten fest,
dass jeder Fehlerfall den Nutzer erreicht.
"""

from unittest.mock import MagicMock, patch

import pytest

import tasks.telegram_task as tt

_PAYLOAD = {
    "voice": {"file_id": "f1", "duration": 5, "mime_type": "audio/ogg"},
    "chat": {"id": 4242},
}


def test_no_file_id_notifies_user():
    with (
        patch.object(tt, "_notify_voice_user") as mock_notify,
        patch.object(tt, "_alert_admin_voice_failure") as mock_alert,
    ):
        from services.voice_transcription import TranscriptionError

        with pytest.raises(TranscriptionError):
            tt._process_voice("log-1", "tenant-1", {"voice": {}, "chat": {"id": 1}})

    mock_notify.assert_called_once()
    mock_alert.assert_called_once()


def test_download_failure_is_transient_and_carries_its_message():
    """Der Text reist an der Ausnahme mit, gesendet wird er erst vom Wrapper —
    sonst laese der Absender bei drei Retries dreimal 'gleich nochmal'."""
    from services.voice_transcription import TranscriptionUnavailable

    with (
        patch.object(tt, "_telegram_get_file", return_value=None),
        patch.object(tt, "_notify_voice_user") as mock_notify,
        patch.object(tt, "_alert_admin_voice_failure") as mock_alert,
    ):
        with pytest.raises(TranscriptionUnavailable) as excinfo:
            tt._process_voice("log-1", "tenant-1", _PAYLOAD)

    assert excinfo.value.user_message == tt._VOICE_MSG_DOWNLOAD
    mock_notify.assert_not_called()
    mock_alert.assert_called_once()


def test_terminal_transcription_error_notifies_user():
    from services.voice_transcription import TranscriptionError

    with (
        patch.object(tt, "_telegram_get_file", return_value=b"audio"),
        patch.object(tt, "transcribe_voice", side_effect=TranscriptionError("HTTP 400")),
        patch.object(tt, "_notify_voice_user") as mock_notify,
        patch.object(tt, "_alert_admin_voice_failure") as mock_alert,
    ):
        with pytest.raises(TranscriptionError):
            tt._process_voice("log-1", "tenant-1", _PAYLOAD)

    mock_notify.assert_called_once()
    mock_alert.assert_called_once()


def test_transient_transcription_error_gets_busy_message_but_no_send():
    from services.voice_transcription import TranscriptionUnavailable

    with (
        patch.object(tt, "_telegram_get_file", return_value=b"audio"),
        patch.object(tt, "transcribe_voice", side_effect=TranscriptionUnavailable("HTTP 429")),
        patch.object(tt, "_notify_voice_user") as mock_notify,
        patch.object(tt, "_alert_admin_voice_failure") as mock_alert,
    ):
        with pytest.raises(TranscriptionUnavailable) as excinfo:
            tt._process_voice("log-1", "tenant-1", _PAYLOAD)

    assert excinfo.value.user_message == tt._VOICE_MSG_BUSY
    mock_notify.assert_not_called()
    mock_alert.assert_called_once()


def test_specific_user_message_wins_over_the_default():
    """'Zu lang' ist eine Ursache, die eine eigene Formulierung verdient."""
    from services.voice_transcription import TranscriptionError

    err = TranscriptionError(
        "Audio zu lang: 200s", user_message="🎤 Die Sprachnachricht ist zu lang."
    )
    with (
        patch.object(tt, "_telegram_get_file", return_value=b"audio"),
        patch.object(tt, "transcribe_voice", side_effect=err),
        patch.object(tt, "_notify_voice_user") as mock_notify,
        patch.object(tt, "_alert_admin_voice_failure"),
    ):
        with pytest.raises(TranscriptionError):
            tt._process_voice("log-1", "tenant-1", _PAYLOAD)

    assert mock_notify.call_args[0][2] == "🎤 Die Sprachnachricht ist zu lang."


def test_technical_detail_never_reaches_the_user():
    """Ein Router-Body gehoert ins Log und in den Alarm, nicht in den Chat."""
    from services.voice_transcription import TranscriptionError

    err = TranscriptionError('HTTP 403: {"error":{"origin":"router","message":"not approved"}}')
    with (
        patch.object(tt, "_telegram_get_file", return_value=b"audio"),
        patch.object(tt, "transcribe_voice", side_effect=err),
        patch.object(tt, "_notify_voice_user") as mock_notify,
        patch.object(tt, "_alert_admin_voice_failure") as mock_alert,
    ):
        with pytest.raises(TranscriptionError):
            tt._process_voice("log-1", "tenant-1", _PAYLOAD)

    assert mock_notify.call_args[0][2] == tt._VOICE_MSG_TRANSCRIBE_FAILED
    assert "403" not in mock_notify.call_args[0][2]
    # Der Betreiber bekommt die technische Ursache sehr wohl.
    assert "403" in mock_alert.call_args[0][1]


def test_empty_transcript_notifies_user():
    from services.voice_transcription import TranscriptionError

    result = MagicMock()
    result.text = "   "
    with (
        patch.object(tt, "_telegram_get_file", return_value=b"audio"),
        patch.object(tt, "transcribe_voice", return_value=result),
        patch.object(tt, "_notify_voice_user") as mock_notify,
        patch.object(tt, "_alert_admin_voice_failure"),
    ):
        with pytest.raises(TranscriptionError):
            tt._process_voice("log-1", "tenant-1", _PAYLOAD)

    mock_notify.assert_called_once()


def test_notify_falls_back_to_resolved_chat_id():
    """Fehlt 'chat' im Payload, waere die Nachricht sonst ohne jede Reaktion zu Ende."""
    with (
        patch.object(tt, "_resolve_chat_id", return_value=99) as mock_resolve,
        patch("api.telegram._send_telegram_message", return_value=True) as mock_send,
    ):
        assert tt._notify_voice_user("tenant-1", {"voice": {}}, "Text") is True

    mock_resolve.assert_called_once_with("tenant-1")
    assert mock_send.call_args[0][0] == 99


def test_notify_without_any_chat_id_is_survivable():
    with (
        patch.object(tt, "_resolve_chat_id", return_value=None),
        patch("api.telegram._send_telegram_message") as mock_send,
    ):
        assert tt._notify_voice_user("tenant-1", {"voice": {}}, "Text") is False

    mock_send.assert_not_called()


def test_notify_survives_malformed_chat_in_payload():
    """'chat' kommt unvalidiert aus original_payload. Ist es kein Dict (kaputter
    String statt {'id': ...}), darf .get('id') die eigentliche TranscriptionError
    nicht durch einen AttributeError ersetzen — fail-open gilt fuer den gesamten
    Funktionsrumpf, nicht nur fuer den Send-Teil."""
    with patch.object(tt, "_resolve_chat_id", return_value=None):
        assert tt._notify_voice_user("tenant-1", {"voice": {}, "chat": "kaputt"}, "Text") is False


def test_admin_alert_is_debounced_per_day():
    """Ohne Entprellung erzeugt ein ausgefallener Dienst einen Alarm pro Nachricht."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = False  # NX schlaegt fehl = heute schon gemeldet

    mock_settings = MagicMock()
    mock_settings.telegram_admin_chat_id = "123"
    mock_settings.redis_url = "redis://localhost:6379/0"

    with (
        patch("tasks.telegram_task.settings", mock_settings),
        patch("redis.from_url", return_value=mock_redis),
        patch("api.telegram._send_admin_telegram_message") as mock_send,
    ):
        tt._alert_admin_voice_failure("tenant-1", "HTTP 429", "transient")

    mock_send.assert_not_called()


def test_admin_alert_sent_on_first_failure_of_the_day():
    mock_redis = MagicMock()
    mock_redis.set.return_value = True

    mock_settings = MagicMock()
    mock_settings.telegram_admin_chat_id = "123"
    mock_settings.redis_url = "redis://localhost:6379/0"

    with (
        patch("tasks.telegram_task.settings", mock_settings),
        patch("redis.from_url", return_value=mock_redis),
        patch("api.telegram._send_admin_telegram_message") as mock_send,
    ):
        tt._alert_admin_voice_failure("tenant-1", "HTTP 429", "transient")

    mock_send.assert_called_once()
    assert "HTTP 429" in mock_send.call_args[0][1]


def test_admin_alert_key_carries_category_and_tenant():
    """Der Key ist das eigentliche Verhalten des Fixes — ihn nicht zu pruefen hiesse,
    den Fix nicht zu pruefen."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True

    mock_settings = MagicMock()
    mock_settings.telegram_admin_chat_id = "123"
    mock_settings.redis_url = "redis://localhost:6379/0"

    with (
        patch("tasks.telegram_task.settings", mock_settings),
        patch("redis.from_url", return_value=mock_redis),
        patch("api.telegram._send_admin_telegram_message"),
    ):
        tt._alert_admin_voice_failure("tenant-1", "HTTP 429", "transient")

    used_key = mock_redis.set.call_args[0][0]
    assert "transient" in used_key
    assert "tenant-1" in used_key


def test_two_different_categories_both_alert_on_the_same_day():
    """Kern des Befunds: ein Bedienfehler (no_file_id) darf den Alarm-Platz des Tages
    nicht fuer einen echten Ausfall (transient) verbrauchen."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True

    mock_settings = MagicMock()
    mock_settings.telegram_admin_chat_id = "123"
    mock_settings.redis_url = "redis://localhost:6379/0"

    with (
        patch("tasks.telegram_task.settings", mock_settings),
        patch("redis.from_url", return_value=mock_redis),
        patch("api.telegram._send_admin_telegram_message") as mock_send,
    ):
        tt._alert_admin_voice_failure("tenant-1", "kein file_id", "no_file_id")
        tt._alert_admin_voice_failure("tenant-1", "HTTP 429", "transient")

    assert mock_send.call_count == 2


def test_admin_alert_never_raises():
    """Fail-open: ein Alarmfehler darf den Fehlerpfad nicht zusaetzlich sprengen."""
    mock_settings = MagicMock()
    mock_settings.telegram_admin_chat_id = "123"
    mock_settings.redis_url = "redis://localhost:6379/0"

    with (
        patch("tasks.telegram_task.settings", mock_settings),
        patch("redis.from_url", side_effect=RuntimeError("redis weg")),
    ):
        tt._alert_admin_voice_failure("tenant-1", "HTTP 429", "transient")  # darf nicht werfen
