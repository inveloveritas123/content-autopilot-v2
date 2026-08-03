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


# ---------------------------------------------------------------------------
# Task-Wrapper: Retry-Verdrahtung
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, retries):
        self.retries = retries


def _fake_task(retries: int):
    """Steht fuer den gebundenen Celery-Task.

    Warum nicht process_telegram_update direkt aufrufen: Ein Task mit bind=True ist ein
    Objekt, dessen __call__ das echte self selbst einsetzt — ein hier uebergebener
    Fake-Task landete als log_id. Deshalb liegt die Retry-Entscheidung in der
    gewoehnlichen Funktion _dispatch_voice, die den Task als Parameter nimmt.
    """
    task = MagicMock()
    task.request = _FakeRequest(retries)
    task.max_retries = 3
    # RuntimeError statt eines echten Retry-Ablaufs: propagiert dieser RuntimeError
    # unveraendert aus _dispatch_voice, kann der letzte-Riegel-`except Exception`
    # dort den Retry nicht abfangen und stillschweigend in "unexpected" verwandeln.
    task.retry.side_effect = RuntimeError("celery-retry")
    return task


def test_transient_failure_triggers_retry_and_notifies_once():
    from services.voice_transcription import TranscriptionUnavailable

    task = _fake_task(retries=0)
    exc = TranscriptionUnavailable("429", user_message="🎤 überlastet")
    with (
        patch.object(tt, "_process_voice", side_effect=exc),
        patch.object(tt, "_notify_voice_user") as mock_notify,
    ):
        with pytest.raises(RuntimeError, match="celery-retry"):
            tt._dispatch_voice(task, "log-1", "tenant-1", _PAYLOAD)

    task.retry.assert_called_once()
    assert task.retry.call_args.kwargs["countdown"] == 30
    mock_notify.assert_called_once()
    assert mock_notify.call_args[0][2] == "🎤 überlastet"


def test_second_retry_does_not_repeat_the_notice():
    """Der Nutzer soll 'gleich nochmal' genau einmal lesen, nicht dreimal."""
    from services.voice_transcription import TranscriptionUnavailable

    task = _fake_task(retries=1)
    with (
        patch.object(tt, "_process_voice", side_effect=TranscriptionUnavailable("429")),
        patch.object(tt, "_notify_voice_user") as mock_notify,
    ):
        with pytest.raises(RuntimeError, match="celery-retry"):
            tt._dispatch_voice(task, "log-1", "tenant-1", _PAYLOAD)

    assert task.retry.call_args.kwargs["countdown"] == 60
    mock_notify.assert_not_called()


def test_third_retry_waits_two_minutes():
    from services.voice_transcription import TranscriptionUnavailable

    task = _fake_task(retries=2)
    with (
        patch.object(tt, "_process_voice", side_effect=TranscriptionUnavailable("429")),
        patch.object(tt, "_notify_voice_user"),
    ):
        with pytest.raises(RuntimeError, match="celery-retry"):
            tt._dispatch_voice(task, "log-1", "tenant-1", _PAYLOAD)

    assert task.retry.call_args.kwargs["countdown"] == 120


def test_exhausted_retries_send_an_honest_final_message():
    """Kein weiteres 'gleich nochmal', wenn es kein 'gleich' mehr gibt."""
    from services.voice_transcription import TranscriptionUnavailable

    task = _fake_task(retries=3)
    with (
        patch.object(tt, "_process_voice", side_effect=TranscriptionUnavailable("429")),
        patch.object(tt, "_notify_voice_user") as mock_notify,
    ):
        result = tt._dispatch_voice(task, "log-1", "tenant-1", _PAYLOAD)

    task.retry.assert_not_called()
    assert result["status"] == "error"
    mock_notify.assert_called_once()
    assert mock_notify.call_args[0][2] == tt._VOICE_MSG_GAVE_UP


def test_terminal_failure_is_not_retried():
    from services.voice_transcription import TranscriptionError

    task = _fake_task(retries=0)
    with (
        patch.object(tt, "_process_voice", side_effect=TranscriptionError("HTTP 400")),
        patch.object(tt, "_notify_voice_user") as mock_notify,
    ):
        result = tt._dispatch_voice(task, "log-1", "tenant-1", _PAYLOAD)

    task.retry.assert_not_called()
    assert result["status"] == "error"
    # Die Meldung kam schon aus _process_voice — hier nicht doppeln.
    mock_notify.assert_not_called()


def test_success_passes_through_untouched():
    task = _fake_task(retries=0)
    with patch.object(tt, "_process_voice", return_value={"status": "ok", "transcript_chars": 42}):
        result = tt._dispatch_voice(task, "log-1", "tenant-1", _PAYLOAD)

    assert result == {"status": "ok", "transcript_chars": 42}
    task.retry.assert_not_called()


def test_unexpected_exception_notifies_and_does_not_retry():
    """Letzter Riegel: ein RuntimeError ist von keiner der beiden spezifischen
    Klauseln abgedeckt — trotzdem muss der Absender eine Antwort bekommen statt
    dass der Task still stirbt."""
    task = _fake_task(retries=0)
    with (
        patch.object(tt, "_process_voice", side_effect=RuntimeError("boom")),
        patch.object(tt, "_notify_voice_user") as mock_notify,
        patch.object(tt, "_alert_admin_voice_failure") as mock_alert,
    ):
        result = tt._dispatch_voice(task, "log-1", "tenant-1", _PAYLOAD)

    task.retry.assert_not_called()
    assert result == {"status": "error", "reason": "unexpected"}
    mock_notify.assert_called_once()
    assert mock_notify.call_args[0][2] == tt._VOICE_MSG_GAVE_UP
    mock_alert.assert_called_once()


def test_soft_time_limit_reaches_the_sender():
    """SoftTimeLimitExceeded erbt von Exception — der letzte Riegel faengt es also,
    und ein vom Soft-Limit getoeteter Task stirbt trotzdem nicht stumm."""
    from celery.exceptions import SoftTimeLimitExceeded

    task = _fake_task(retries=0)
    with (
        patch.object(tt, "_process_voice", side_effect=SoftTimeLimitExceeded()),
        patch.object(tt, "_notify_voice_user") as mock_notify,
        patch.object(tt, "_alert_admin_voice_failure") as mock_alert,
    ):
        result = tt._dispatch_voice(task, "log-1", "tenant-1", _PAYLOAD)

    task.retry.assert_not_called()
    assert result == {"status": "error", "reason": "unexpected"}
    mock_notify.assert_called_once()
    assert mock_notify.call_args[0][2] == tt._VOICE_MSG_GAVE_UP
    mock_alert.assert_called_once()


def test_process_telegram_update_decorator_matches_the_owner_decision():
    """Einzige Stelle, die den echten Decorator prueft — nicht als vermeintlich
    redundant loeschen. _fake_task oben codiert max_retries=3 hart statt es vom
    echten Task abzuleiten; ohne diesen Test wuerde ein Revert des Decorators
    auf z. B. max_retries=1 alle Tests gruen lassen, waehrend Produktion nur
    noch einmal statt dreimal retryt — der stille Fehlermodus, den dieser
    Branch beseitigen soll."""
    opts = tt.process_telegram_update.celery_opts
    assert opts["max_retries"] == 3
    assert opts["soft_time_limit"] == 1200
    assert opts["time_limit"] == 1260
