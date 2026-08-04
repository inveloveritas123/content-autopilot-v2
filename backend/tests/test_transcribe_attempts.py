"""Versuchszaehler und is_active-Riegel fuer batch_transcribe.

Hintergrund 03.08.2026: 168 aussichtslose Podcast-Episoden liefen alle 30 Minuten
erneut (394s Laufzeit, 168/168 Fehlschlaege) und verbrannten das Ratenlimit, an dem
dann eine echte Sprachnachricht starb. Beide Podcast-Quellen waren dabei bereits
is_active=false — der Task geht aber ueber source_items, nicht ueber sources.
"""

from unittest.mock import MagicMock


def test_max_attempts_is_three():
    from tasks.transcribe_task import MAX_TRANSCRIPTION_ATTEMPTS

    assert MAX_TRANSCRIPTION_ATTEMPTS == 3


def test_batch_query_excludes_exhausted_and_inactive():
    """Der Query muss beide Riegel tragen: Zaehler UND is_active.

    Geprueft wird die kompilierte SQL, nicht das Verhalten einer echten DB —
    hier geht es genau darum, dass die Bedingungen im Statement stehen.
    """
    from tasks.transcribe_task import _build_batch_query

    sql = str(_build_batch_query(None).compile(compile_kwargs={"literal_binds": True}))

    assert "transcription_attempts <" in sql
    assert "is_active" in sql
    assert "transcription_abandoned" not in sql, (
        "Der Endzustand darf NICHT im Eingangsfilter stehen — sonst ist die "
        "Endlosschleife zurueck."
    )


def test_failure_increments_and_abandons_at_limit():
    from tasks.transcribe_task import MAX_TRANSCRIPTION_ATTEMPTS, _apply_failure

    item = MagicMock()
    item.transcription_attempts = MAX_TRANSCRIPTION_ATTEMPTS - 1
    _apply_failure(item)

    assert item.transcription_attempts == MAX_TRANSCRIPTION_ATTEMPTS
    assert item.status == "transcription_abandoned"


def test_failure_below_limit_stays_retryable():
    from tasks.transcribe_task import _apply_failure

    item = MagicMock()
    item.transcription_attempts = 0
    _apply_failure(item)

    assert item.transcription_attempts == 1
    assert item.status == "transcription_failed"


def test_success_resets_counter():
    from tasks.transcribe_task import _apply_success

    item = MagicMock()
    item.transcription_attempts = 2
    _apply_success(item, "Ein Transkript.", "podcast")

    assert item.transcription_attempts == 0
    assert item.status == "transcribed"
    assert item.transcript_text == "Ein Transkript."


def test_abandoned_is_visible_in_the_error_group():
    """Sonst passiert genau das, was den 168 'skipped'-Items passiert ist:
    Loop gestoppt, aber im UI unter keinem Filter mehr auffindbar."""
    from api.activity import STATUS_GROUP_MAP

    assert "transcription_abandoned" in STATUS_GROUP_MAP["error"]


def test_single_task_accepts_abandoned_for_manual_restart():
    """Ein Mensch, der bewusst neu anstoesst, darf nicht vom Zaehler blockiert sein."""
    from tasks.transcribe_task import RETRYABLE_STATUSES

    assert "transcription_abandoned" in RETRYABLE_STATUSES
