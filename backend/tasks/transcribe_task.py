import asyncio
import logging

from sqlalchemy import func, select

from models.base import sync_session_factory
from models.source import Source
from models.source_item import SourceItem
from services.rls import set_rls_bypass_sync, set_rls_tenant_sync
from services.transcription import transcribe_content
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

MAX_TRANSCRIPTION_ATTEMPTS = 3

# Eingangsfilter des Batch-Laufs. `transcription_abandoned` steht hier bewusst NICHT:
# Der Endzustand darf kein Eingangszustand sein, sonst ist die Schleife zurück.
BATCH_STATUSES = ("new", "transcription_failed", "needs_voicescriptor")

# Der Einzel-Task nimmt zusätzlich den Endzustand — ein Mensch, der bewusst neu
# anstößt, soll nicht vom Zähler blockiert werden.
RETRYABLE_STATUSES = (*BATCH_STATUSES, "transcription_abandoned")


def _build_batch_query(tenant_id: str | None):
    """Items, die einen weiteren Transkriptionsversuch verdienen.

    Zwei Riegel, bewusst unabhängig voneinander:
      1. Versuchszähler — stoppt aussichtslose Items.
      2. sources.is_active — stoppt ganze Quellen. Am 03.08.2026 waren beide
         Podcast-Quellen bereits inaktiv, ohne dass es den Loop gestoppt hätte,
         weil der Query über source_items geht und sources nie ansieht.
    """
    query = (
        select(SourceItem)
        .join(Source, Source.id == SourceItem.source_id)
        .where(
            SourceItem.status.in_(BATCH_STATUSES),
            SourceItem.transcription_attempts < MAX_TRANSCRIPTION_ATTEMPTS,
            Source.is_active.is_(True),
        )
    )
    if tenant_id:
        query = query.where(SourceItem.tenant_id == tenant_id)
    return query.order_by(SourceItem.created_at.asc())


def _apply_failure(item) -> None:
    """Zählt den Fehlversuch und gibt beim Erreichen des Maximums auf."""
    item.transcription_attempts = (item.transcription_attempts or 0) + 1
    if item.transcription_attempts >= MAX_TRANSCRIPTION_ATTEMPTS:
        item.status = "transcription_abandoned"
    else:
        item.status = "transcription_failed"


def _apply_success(item, transcript_text: str, source_type: str) -> None:
    """Erfolg setzt den Zähler zurück — eine später erneut eingereihte Quelle startet frisch."""
    item.transcript_text = transcript_text
    item.transcript_source = f"{source_type}_api"
    item.status = "transcribed"
    item.transcription_attempts = 0


def _enqueue_transcript_observer(tenant_id, source_item_id) -> None:
    """Stößt den P17 je-Transkript-Beobachter an (#41) — parallel zur Analyse, fail-open.

    Der Beobachter schlägt inkrementelle Voice/Werte/Avatar-Updates vor (Board Bahn 5).
    Ein Enqueue-Fehler darf den Transkriptions-Pfad nie blockieren.
    """
    try:
        from tasks.p17_transcript_observer_task import observe_transcript

        observe_transcript.delay(str(tenant_id), str(source_item_id))
    except Exception as obs_err:
        logger.warning("P17 observer enqueue failed for %s: %s", source_item_id, obs_err)


@celery_app.task(name="tasks.transcribe_task.transcribe_item")
def transcribe_item(item_id: str):
    """Transcribe a single source item — supports YouTube and Podcast."""
    with sync_session_factory() as session:
        # Der Task bekommt nur die item_id — die tenant_id steht erst NACH dem
        # Laden zur Verfuegung. Ohne Kontext liefert session.get() unter FORCE
        # ROW LEVEL SECURITY None, und der Task meldet "not_found" fuer ein Item,
        # das existiert. Bypass NUR fuer den PK-Read, danach eng weiter.
        set_rls_bypass_sync(session, True)
        item = session.get(SourceItem, item_id)
        if not item:
            return {"item_id": item_id, "status": "not_found"}
        set_rls_bypass_sync(session, False)
        # Einmal festhalten: nach jedem commit() muss der Kontext erneuert
        # werden, und `item.tenant_id` waere dann selbst ein Lazy-Load ohne
        # Kontext — also den Wert jetzt sichern, solange er sicher lesbar ist.
        tenant_id_str = str(item.tenant_id)
        set_rls_tenant_sync(session, tenant_id_str)

        if item.status not in RETRYABLE_STATUSES:
            return {"item_id": item_id, "status": item.status, "skipped": True}

        # Reset gilt NUR fuer den Wiedereinstieg aus dem Endzustand — ein Reset bei
        # jedem Eintritt wuerde das Hochzaehlen fuer normale Einzel-Retries zerstoeren
        # und der Abbruch kaeme nie zustande.
        if item.status == "transcription_abandoned":
            item.transcription_attempts = 0

        item.status = "transcribing"
        session.commit()
        # ⛔ SET LOCAL verfaellt beim Commit — ohne Erneuerung liefe der gesamte
        # Rest dieser Funktion (Source-Lookup, QualityMetric-Insert, die beiden
        # Abschluss-Commits) ohne Kontext und damit auf 0 Zeilen.
        set_rls_tenant_sync(session, tenant_id_str)

        source = session.get(Source, item.source_id)
        source_type = source.type if source else "youtube"

        # Route to unified transcription interface
        transcript_text = asyncio.run(
            transcribe_content(
                source_type=source_type,
                external_id=item.external_id,
                url=item.url or "",
                audio_url=item.audio_url or (item.url if source_type == "podcast" else ""),
                language=source.language if source else "de",
                content_text=item.transcript_text or "",
            )
        )

        if transcript_text:
            _apply_success(item, transcript_text, source_type)
            session.commit()
            # ⛔ Kontext nach dem Commit erneuern — sonst laeuft der
            # QualityMetric-Insert darunter ohne Kontext und verschwindet.
            set_rls_tenant_sync(session, tenant_id_str)

            # Auto-score transcription quality
            try:
                from models.quality_metric import QualityMetric
                from services.quality_scorer import score_transcription

                scores = score_transcription(transcript_text)
                # Transcription uses yt-dlp/VoiceScriptor (no LLM), mark source
                transcript_src = item.transcript_source or "yt_auto"
                model_label = (
                    "voicescriptor"
                    if "voicescriptor" in transcript_src
                    else "yt_manual"
                    if "manual" in transcript_src
                    else "yt_auto"
                )
                qm = QualityMetric(
                    source_item_id=item.id,
                    tenant_id=item.tenant_id,
                    step="transcription",
                    model_used=model_label,
                    completeness_score=scores.get("completeness_score"),
                    accuracy_score=scores.get("accuracy_score"),
                    overall_score=scores.get("overall_score"),
                )
                session.add(qm)
                session.commit()
            except Exception as qe:
                logger.warning(f"Quality scoring failed for transcription {item_id}: {qe}")

            # Auto-chain: analyze
            from tasks.generate_task import analyze_item

            analyze_item.delay(item_id)
            # Parallel: P17 je-Transkript-Beobachter (#41)
            _enqueue_transcript_observer(item.tenant_id, item.id)
            return {"item_id": item_id, "status": "transcribed", "source": f"{source_type}_api"}
        else:
            _apply_failure(item)
            session.commit()
            return {"item_id": item_id, "status": item.status}


@celery_app.task(name="tasks.transcribe_task.batch_transcribe")
def batch_transcribe(tenant_id: str | None = None):
    """Batch transcribe 'new' items via unified transcribe_content() — full 4-step fallback chain."""
    with sync_session_factory() as session:
        # `tenant_id` ist optional: ohne Argument laeuft der Batch bewusst ueber
        # ALLE Tenants (Cron), mit Argument ueber einen. Entsprechend der enge
        # oder der breite Weg — `source_items` traegt seit Migration 058 FORCE
        # ROW LEVEL SECURITY und lieferte sonst 0 Items, ununterscheidbar von
        # "nichts zu transkribieren".
        if tenant_id:
            set_rls_tenant_sync(session, tenant_id)
        else:
            set_rls_bypass_sync(session, True)
        items = session.execute(_build_batch_query(tenant_id)).scalars().all()
        total = len(items)
        success = 0
        failed = 0

        logger.info(f"=== BATCH START: {total} items to transcribe ===")

        for i, item in enumerate(items):
            item.status = "transcribing"
            session.commit()
            # ⛔ SET LOCAL verfaellt beim Commit — ohne Erneuerung liefe der Rest
            # dieser Iteration und jede weitere ohne Kontext (0 Zeilen).
            if tenant_id:
                set_rls_tenant_sync(session, tenant_id)
            else:
                set_rls_bypass_sync(session, True)

            source = session.get(Source, item.source_id)
            source_type = source.type if source else "youtube"

            transcript_text = asyncio.run(
                transcribe_content(
                    source_type=source_type,
                    external_id=item.external_id,
                    url=item.url or "",
                    audio_url=item.audio_url or (item.url if source_type == "podcast" else ""),
                    language=source.language if source else "de",
                    content_text=item.transcript_text or "",
                )
            )

            if transcript_text:
                _apply_success(item, transcript_text, source_type)
                success += 1
                logger.info(f"[{success}/{total}] OK: {item.title[:60]}")
                from tasks.generate_task import analyze_item

                analyze_item.delay(item.id)
                # Parallel: P17 je-Transkript-Beobachter (#41)
                _enqueue_transcript_observer(item.tenant_id, item.id)
            else:
                _apply_failure(item)
                failed += 1
                logger.warning(
                    f"[{i + 1}/{total}] FAILED ({item.transcription_attempts}/"
                    f"{MAX_TRANSCRIPTION_ATTEMPTS}): {item.title[:60]}"
                )

            session.commit()
            # ⛔ Kontext nach dem Commit erneuern — die naechste Iteration und
            # die Schluss-Zaehlung unten liefen sonst ohne Kontext.
            if tenant_id:
                set_rls_tenant_sync(session, tenant_id)
            else:
                set_rls_bypass_sync(session, True)

        remaining = (
            session.execute(
                select(func.count(SourceItem.id)).where(SourceItem.status == "new")
            ).scalar()
            or 0
        )

        result = {"total": total, "success": success, "failed": failed, "remaining_new": remaining}
        logger.info(f"=== BATCH DONE: {result} ===")
        return result
