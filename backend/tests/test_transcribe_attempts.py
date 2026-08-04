"""Versuchszaehler und is_active-Riegel fuer batch_transcribe.

Hintergrund 03.08.2026: 168 aussichtslose Podcast-Episoden liefen alle 30 Minuten
erneut (394s Laufzeit, 168/168 Fehlschlaege) und verbrannten das Ratenlimit, an dem
dann eine echte Sprachnachricht starb. Beide Podcast-Quellen waren dabei bereits
is_active=false — der Task geht aber ueber source_items, nicht ueber sources.
"""

import asyncio
import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch


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


# ---------------------------------------------------------------------------
# Task 9 — Zaehler-Reset zentral verankern (Lueckenschluss transcribe_item + update_item)
# ---------------------------------------------------------------------------


def _fake_item(status: str, attempts: int):
    """Baut ein Item-Double fuer transcribe_item — kein echtes Model, nur Attribute."""
    item = MagicMock()
    item.id = "item-1"
    item.status = status
    item.transcription_attempts = attempts
    item.source_id = "source-1"
    item.tenant_id = "tenant-1"
    item.external_id = "ext-1"
    item.url = "https://example.com/ep"
    item.audio_url = None
    item.transcript_text = None
    return item


def _run_transcribe_item_with_failure(item):
    """Fuehrt tasks.transcribe_task.transcribe_item mit gemocktem Session-/Transcribe-Pfad
    aus und simuliert einen fehlgeschlagenen Transkriptionsversuch (transcribe_content
    liefert None). Damit landet die Ausfuehrung immer im _apply_failure-Zweig, ohne
    echten DB- oder Netzwerkzugriff."""
    from models.source_item import SourceItem
    from tasks import transcribe_task as tt

    source = MagicMock()
    source.type = "podcast"
    source.language = "de"

    def _session_get(model, _id):
        return item if model is SourceItem else source

    session = MagicMock()
    session.get.side_effect = _session_get
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    with (
        patch.object(tt, "sync_session_factory", return_value=session),
        patch.object(tt, "transcribe_content", new=AsyncMock(return_value=None)),
    ):
        tt.transcribe_item(item.id)


def test_transcribe_item_resets_counter_on_reentry_from_abandoned():
    """Wiedereinstieg aus transcription_abandoned setzt den Zaehler auf 0, BEVOR der
    Fehlversuch gezaehlt wird — sonst waere es der eine Versuch statt der zugesagten drei."""
    item = _fake_item(status="transcription_abandoned", attempts=3)

    _run_transcribe_item_with_failure(item)

    assert (
        item.transcription_attempts == 1
    ), "Reset fehlt oder greift nicht: 3 (alt) + 1 (Fehlversuch) waere wieder 4."
    assert item.status == "transcription_failed"


def test_transcribe_item_does_not_reset_counter_on_normal_reentry():
    """Mutationsschutz fuer den Test oben: ein Reset bei JEDEM Eintritt (nicht nur aus
    transcription_abandoned) wuerde das Hochzaehlen fuer normale Einzel-Retries zerstoeren."""
    item = _fake_item(status="transcription_failed", attempts=1)

    _run_transcribe_item_with_failure(item)

    assert (
        item.transcription_attempts == 2
    ), "Zaehler wurde bei normalem Wiedereinstieg zurueckgesetzt statt hochgezaehlt."
    assert item.status == "transcription_failed"


def _make_update_item_db(item):
    db = MagicMock()
    db.get = AsyncMock(return_value=item)
    db.commit = AsyncMock()
    return db


def test_update_item_resets_counter_for_batch_status():
    """PATCH auf einen BATCH_STATUSES-Wert macht das Item wieder eingangsfaehig fuer den
    Batch-Lauf — ohne Reset bliebe es trotzdem fuer immer ausgeschlossen, weil
    _build_batch_query ueber transcription_attempts filtert."""
    from api.items import ItemUpdate, update_item
    from tasks.transcribe_task import BATCH_STATUSES

    tenant_id = uuid.uuid4()
    item = MagicMock()
    item.tenant_id = tenant_id
    item.transcription_attempts = 3

    db = _make_update_item_db(item)
    tenant = types.SimpleNamespace(id=tenant_id)
    target_status = BATCH_STATUSES[0]

    asyncio.run(
        update_item(
            item_id=str(uuid.uuid4()),
            data=ItemUpdate(status=target_status),
            tenant=tenant,
            db=db,
        )
    )

    assert item.status == target_status
    assert item.transcription_attempts == 0


def test_update_item_other_field_leaves_counter_untouched():
    """Mutationsschutz: ein PATCH ohne status (z. B. nur is_archived) darf den Zaehler
    nicht anfassen."""
    from api.items import ItemUpdate, update_item

    tenant_id = uuid.uuid4()
    item = MagicMock()
    item.tenant_id = tenant_id
    item.transcription_attempts = 3

    db = _make_update_item_db(item)
    tenant = types.SimpleNamespace(id=tenant_id)

    asyncio.run(
        update_item(
            item_id=str(uuid.uuid4()),
            data=ItemUpdate(is_archived=True),
            tenant=tenant,
            db=db,
        )
    )

    assert item.transcription_attempts == 3
