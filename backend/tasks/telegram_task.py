"""Telegram-Update-Verarbeitung (Phase 5 Welle 3, Issue #140).

Wird von api.telegram._store_and_dispatch() per Celery enqueued.
Lädt das telegram_message_log-Row, holt Audio/Photo via getFile-API,
transkribiert (Voice) bzw. OCR+Vision (Photo, später Welle 4),
schreibt das Resultat als memory_chunk und persistiert
transcript_text + transcription_model im log-Row.

Defensiv:
- Bei jedem Schritt soft-fail mit logger.warning
- Embedding-Fehler blockieren NICHT (chunk-without-embedding,
  HNSW-Index PARTIAL)
"""

from __future__ import annotations

import asyncio
import logging
import os
import types

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models.base import sync_session_factory
from services.voice_transcription import (
    TranscriptionError,
    TranscriptionResult,
    transcribe_voice,
)
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


# ── helpers ─────────────────────────────────────────────────────────────


def _load_log_row(log_id: str) -> dict | None:
    """Lädt eine telegram_message_log-Zeile als Dict."""
    with sync_session_factory() as db:
        row = db.execute(
            text(
                "SELECT id, tenant_id, message_type, original_payload, "
                "       transcript_text, transcription_model "
                "FROM telegram_message_log WHERE id = :id"
            ),
            {"id": log_id},
        ).fetchone()
    if row is None:
        return None
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "message_type": row.message_type,
        "original_payload": dict(row.original_payload or {}),
        "transcript_text": row.transcript_text,
        "transcription_model": row.transcription_model,
    }


def _update_log_transcript(log_id: str, transcript: str, model: str, confidence: float) -> None:
    with sync_session_factory() as db:
        db.execute(
            text(
                "UPDATE telegram_message_log "
                "SET transcript_text = :t, transcription_model = :m, "
                "    transcription_confidence = :c "
                "WHERE id = :id"
            ),
            {"id": log_id, "t": transcript, "m": model, "c": round(min(max(confidence, 0), 1), 2)},
        )
        db.commit()


def _load_active_session(tenant_id: str) -> object | None:
    """Lädt die aktive bot_session des Tenants (random_smart oder targeted).

    Gibt ein leichtgewichtiges SimpleNamespace(id, status, current_question)
    zurück (KEIN ORM-Model — route_telegram_intent greift nur per
    getattr/str auf id/status zu) oder None, wenn keine aktive Session
    existiert.

    #57: Filter auf mode IN ('random_smart','targeted') erweitert — ohne dies
    umgehen targeted-Antworten still das p08-Routing (p08_service unterstützt
    targeted bereits).

    #62: current_question (letzte bot-Frage aus messages[-1]["bot"]) wird
    mitgeladen, damit Layer-1 die Nutzer-Antwort gegen die tatsächlich
    gestellte Frage klassifizieren kann statt blind zu raten.
    """
    with sync_session_factory() as db:
        row = db.execute(
            text(
                "SELECT id, status, messages FROM bot_session "
                "WHERE tenant_id = :tid AND status = 'active' "
                "      AND mode IN ('random_smart', 'targeted') "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"tid": tenant_id},
        ).fetchone()
    if row is None:
        return None
    current_question = ""
    messages = row.messages or []
    if isinstance(messages, list) and messages:
        last_entry = messages[-1]
        if isinstance(last_entry, dict):
            current_question = (last_entry.get("bot") or "").strip()
    return types.SimpleNamespace(id=row.id, status=row.status, current_question=current_question)


def _is_pending_variant_choice(tenant_id: str, text_content: str) -> bool:
    """True nur bei OFFENEM Varianten-Marker UND parsebarem Wahl-Token.

    Beide Bedingungen zusammen. Ein reiner Marker-Check wäre falsch: der Marker
    lebt 24 Stunden (`_P13_CHOICE_WINDOW_HOURS`), ein veralteter würde die Weiche
    kippen und damit ausgerechnet den LLM-Pfad wieder öffnen, den
    `_awaits_user_choice` schließt.

    Token zuerst — reines Regex, spart den DB-Treffer im Normalfall.
    """
    try:
        from tasks.p13_variants_task import _load_pending_idea, _parse_choice_token

        if _parse_choice_token(text_content) is None:
            return False
        return _load_pending_idea(tenant_id) is not None
    except Exception as exc:
        logger.warning("pending variant check failed: %s", type(exc).__name__)
        return False


def _awaits_user_choice(tenant_id: str, text_content: str) -> bool:
    """True = der Nutzer muss entscheiden, was mit der Nachricht passieren soll.

    Ersetzt den LLM-Rateschritt: statt zu klassifizieren, was jemand wollte, fragt
    der Bot nach. Nur wenn ein bestehender Pfad die Nachricht nachweislich
    erwartet, bleibt es beim alten Verhalten.

    Fail-open zu False, und die Richtung ist Absicht: Wirft z. B.
    `_load_active_session`, wissen wir nicht, ob ein Interview läuft. False führt
    zurück in `_route_inbound_message`, das die Session selbst noch einmal lädt —
    eine laufende Antwort geht also nicht verloren. True („im Zweifel fragen")
    wäre hier gefährlicher: es würde die Antwort auf eine offene Interview-Frage
    verwerfen und das Gespräch stehen lassen.
    """
    try:
        if _load_active_session(tenant_id) is not None:
            return False

        from services.chat_intent_heuristics import is_idea_request

        if is_idea_request(text_content):
            return False

        return not _is_pending_variant_choice(tenant_id, text_content)
    except Exception as exc:
        logger.warning("choice gate failed: %s", type(exc).__name__)
        return False


def _send_choice_prompt(
    tenant_id: str, chat_id: int, log_id: str, text_content: str, icon: str
) -> bool:
    """Bestätigung plus die zwei Wege. True, wenn zugestellt.

    Kein Rollback nötig, wenn der Versand scheitert: es wurde keine Session
    eröffnet, die als Falle zurückbliebe, und der Memory-Chunk liegt bereits.
    Aber protokollieren statt schlucken — dieser Prompt ist der einzige sichtbare
    Ausgang der Nachricht.
    """
    preview = text_content[:80].rstrip()
    suffix = "…" if len(text_content) > 80 else ""
    try:
        from api.telegram import _choice_keyboard, _send_telegram_message

        sent = _send_telegram_message(
            chat_id,
            f"{icon} Notiert: „{preview}{suffix}“\n\nWas soll ich damit machen?",
            tenant_id=tenant_id,
            reply_markup=_choice_keyboard(log_id),
        )
    except Exception as exc:
        logger.warning("choice prompt send failed: %s", type(exc).__name__)
        return False
    if not sent:
        logger.warning(
            "telegram_task: Wahl-Prompt nicht zugestellt (tenant=%s, log_id=%s)",
            tenant_id,
            log_id,
        )
    return sent


def _resolve_chat_id(tenant_id: str) -> int | None:
    """Lookup active Telegram chat_id for a tenant (Issue #17).

    1:1 nach dem Muster random_smart_scheduler._send_opening_question.
    Fail-open: gibt None zurück bei Fehler oder wenn kein aktiver Link.
    E2: nur type(e).__name__ loggen, nie str(exc).
    """
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT telegram_chat_id FROM tenant_telegram_link "
                    "WHERE tenant_id = :tid AND status = 'active' LIMIT 1"
                ),
                {"tid": tenant_id},
            ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return None
    except Exception as exc:
        logger.warning("_resolve_chat_id failed: %s", type(exc).__name__)
        return None


_FEEDBACK_WINDOW_HOURS = int(os.environ.get("TELEGRAM_FEEDBACK_WINDOW_HOURS", "48"))


def _resolve_last_post(tenant_id: str) -> object | None:
    """Löst den jüngsten Bot-Post (bot_session_close oder post_feedback_regen) auf.

    Zeitfenster: TELEGRAM_FEEDBACK_WINDOW_HOURS (Default 48h).
    Liefert SimpleNamespace(id, summary, bot_session_id) oder None.
    Fail-open (E2): nur type(exc).__name__ loggen. Tenant-gescopet (E3).

    #37: migrationsfrei — nutzt content_metadata->>'source' IN ('bot_session_close',
    'post_feedback_regen'), Marker aus #19 (session_post_task.py:192).
    """
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT id, content_text, content_metadata->>'bot_session_id' AS bot_session_id "
                    "FROM content_pieces "
                    "WHERE tenant_id = :tid "
                    "  AND content_metadata->>'source' IN ('bot_session_close', 'post_feedback_regen') "
                    "  AND created_at > now() - make_interval(hours => :window_hours) "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"tid": tenant_id, "window_hours": _FEEDBACK_WINDOW_HOURS},
            ).fetchone()
        if row is None:
            return None
        return types.SimpleNamespace(
            id=str(row.id),
            summary=(row.content_text or "")[:200],
            bot_session_id=str(row.bot_session_id) if row.bot_session_id else None,
        )
    except Exception as exc:
        logger.warning("_resolve_last_post failed: %s", type(exc).__name__)
        return None


def _route_inbound_message(
    tenant_id: str, text_content: str, log_id: str | None = None
) -> dict | None:
    """Verdrahtet eingehende Antworten mit der Intent-Routing-Pipeline (Issue #16).

    Schritt 1: Idempotenz-Guard — wenn log_id gesetzt und routed_to bereits
               non-NULL → Duplikat, früh return (kein zweiter p08-Call). (#56/#18)
    Schritt 2: aktive Session laden (PRIMÄRES Gate). Keine Session → None.
    Schritt 3: extract_intent_features → route_telegram_intent.
    Schritt 4: Routing-Marker persistieren BEVOR p08_response (at-most-once,
               damit ein Crash mitten in p08 beim Retry nicht erneut routet). (#56)
    Schritt 5: bei target == 'p08_response' → p08_response aufrufen.

    Fail-open: jede Exception wird nur geloggt, Rückgabe None — der bestehende
    Chunk-Return des Callers darf NIEMALS kaputtgehen.

    Returns ein Dict mit Routing-Metadaten (z.B. routed_to, p08_next_action,
    bot_session_id) oder None, wenn nicht geroutet wurde.
    """
    try:
        # #56/#18 Schicht A — Idempotenz-Guard: bereits geroutete Log-Zeile überspringen
        if log_id is not None:
            with sync_session_factory() as db:
                guard_row = db.execute(
                    text("SELECT routed_to FROM telegram_message_log WHERE id = :id"),
                    {"id": log_id},
                ).fetchone()
            if guard_row is not None and guard_row[0] is not None:
                # Bereits geroutet — Celery-Retry oder Doppel-Event → überspringen
                logger.info(
                    "inbound routing deduplicated: log_id=%s already routed_to=%s",
                    log_id,
                    guard_row[0],
                )
                return {"routed_to": guard_row[0], "deduped": True}

        # #36 Gate 2 — P13-Choice: Pending-Marker + strenges Choice-Pattern (≤40 Zeichen).
        # VOR Gate 3 (aktive Session): zwischen Varianten-Nachricht und Wahl kann der
        # random_smart-Scheduler eine Session öffnen — „2" darf nicht als p08-Antwort landen.
        # Strenge Länge (≤40 Zeichen) macht Fehlgriffe auf echte Interview-Antworten
        # praktisch unmöglich; lange Antworten fallen durch zu Gate 3.
        try:
            from tasks.p13_variants_task import _try_p13_variant_choice

            choice_result = _try_p13_variant_choice(tenant_id, text_content)
            if choice_result and isinstance(choice_result, dict):
                if log_id is not None:
                    from services.layer2_routing import (
                        RoutingDecision,
                        persist_routing_decision,
                    )

                    _p13_dec = RoutingDecision("p13_variants", {}, "p13_choice")
                    persist_routing_decision(log_id, _p13_dec)
                return choice_result
        except Exception as exc:
            logger.warning("p13 choice gate failed: %s", type(exc).__name__)
            # Fail-open: weiter mit normalem Flow

        session = _load_active_session(tenant_id)
        if session is None:
            # #36 Gate 4 — P09-Heuristik: vor _resolve_last_post, damit der
            # 48h-Feedback-Pfad (#37) Ideen-Anfragen nicht frisst.
            # Deterministisch, kein LLM-Call (dep-freie Heuristik).
            try:
                from services.chat_intent_heuristics import is_idea_request
                from tasks.p09_chat_ideas_task import deliver_ideas_to_chat

                if is_idea_request(text_content):
                    deliver_ideas_to_chat.apply_async(args=[tenant_id, text_content[:500], log_id])
                    if log_id is not None:
                        # Persist-Marker (at-most-once, Dedup-Guard); fail-open wenn
                        # CHECK-Constraint den p10-Mapped-Wert ablehnt.
                        from services.layer2_routing import (
                            RoutingDecision,
                            persist_routing_decision,
                        )

                        _dec = RoutingDecision("p09_ideation", {}, "p09_heuristic")
                        persist_routing_decision(log_id, _dec)
                    return {"routed_to": "p09_ideation", "p09_enqueued": True}
            except Exception as exc:
                logger.warning("p09 heuristic gate failed: %s", type(exc).__name__)
                # Fail-open: weiter mit normalem Flow

            # #37 — Feedback-Zweig: kein aktives Session-Objekt, aber letzter Post vorhanden?
            last_post = _resolve_last_post(tenant_id)
            if last_post is None:
                # #36 Gate 6 — Own-Idea-Vorfilter: hält heutiges LLM-Kostenprofil —
                # kein Layer1-Call für reine Memory-Inputs.
                # Nur bei is_own_idea-Treffer → Layer1 → Layer2 (spontaneous_idea ohne
                # Session → p13_variants). Kein Treffer → Memory-Default wie bisher.
                try:
                    from services.chat_intent_heuristics import is_own_idea
                    from services.layer1_extraction import extract_intent_features
                    from services.layer2_routing import (
                        persist_routing_decision,
                        route_telegram_intent,
                    )
                    from tasks.p13_variants_task import generate_variants_for_chat

                    if is_own_idea(text_content):
                        extraction = extract_intent_features(
                            transcript=text_content,
                            tenant_id=tenant_id,
                            session_state="no_session",
                        )
                        decision = route_telegram_intent(
                            extraction, tenant_id, current_session=None
                        )
                        if log_id is not None:
                            persist_routing_decision(log_id, decision)
                        if decision.target == "p13_variants":
                            generate_variants_for_chat.apply_async(
                                args=[tenant_id, text_content[:1000], log_id]
                            )
                            return {"routed_to": "p13_variants", "p13_enqueued": True}
                        # reviewer_queue / flagged → Marker bereits gesetzt, kein Chat-Spam
                        return {"routed_to": decision.target}
                except Exception as exc:
                    logger.warning("p13 own-idea gate failed: %s", type(exc).__name__)
                    # Fail-open: Memory-Default
                return None  # Verhalten wie bisher: keine Session, kein Post → None

            from services.layer1_extraction import extract_intent_features
            from services.layer2_routing import persist_routing_decision, route_telegram_intent

            extraction = extract_intent_features(
                transcript=text_content,
                tenant_id=tenant_id,
                session_state="no_session",
                last_post_summary=last_post.summary,
            )
            decision = route_telegram_intent(extraction, tenant_id, last_post_id=last_post.id)
            if log_id is not None:
                persist_routing_decision(log_id, decision)
            if decision.target == "voice_feedback_api":
                try:
                    from tasks.post_feedback_task import regenerate_post_from_feedback

                    regenerate_post_from_feedback.apply_async(
                        args=[last_post.id, tenant_id, text_content, log_id]
                    )
                    return {"routed_to": "voice_feedback_api", "regen_enqueued": True}
                except Exception as exc:
                    logger.warning("feedback regen enqueue failed: %s", type(exc).__name__)
                    return {"routed_to": "voice_feedback_api", "regen_enqueued": False}
            if decision.target == "p13_variants":
                # #36 Gate 5 — P13-Zweig im last_post-Kontext
                try:
                    from tasks.p13_variants_task import generate_variants_for_chat

                    generate_variants_for_chat.apply_async(
                        args=[tenant_id, text_content[:1000], log_id]
                    )
                    return {"routed_to": "p13_variants", "p13_enqueued": True}
                except Exception as exc:
                    logger.warning("p13 variants enqueue failed: %s", type(exc).__name__)
                    return {"routed_to": "p13_variants", "p13_enqueued": False}
            # Andere Targets: Routing-Marker setzen, kein Chat-Spam
            return {"routed_to": decision.target}

        from services.layer1_extraction import extract_intent_features
        from services.layer2_routing import persist_routing_decision, route_telegram_intent

        extraction = extract_intent_features(
            transcript=text_content,
            tenant_id=tenant_id,
            session_state="active",
            current_question=getattr(session, "current_question", ""),
        )
        decision = route_telegram_intent(extraction, tenant_id, current_session=session)

        # #56: Routing-Marker VOR dem LLM-Call setzen (at-most-once für p08_response).
        # Fail-open: persist_routing_decision fängt intern alle Exceptions.
        # Nur p08_response ist CHECK-konform persistierbar (B11); für andere
        # Targets scheitert das UPDATE im Constraint still (fail-open eingebaut).
        if log_id is not None:
            persist_routing_decision(log_id, decision)

        routing_info: dict = {"routed_to": decision.target, "bot_session_id": str(session.id)}

        if decision.target == "p08_response":
            from services.p08_service import p08_response

            # #19: Roh-Transkript durchreichen → p08 persistiert es in
            # bot_session.messages[*].user_transcript für die Post-Generierung
            # (Schicht-3-Grenze bleibt in p08_response gewahrt).
            result = p08_response(
                decision.payload["session_id"],
                decision.payload["features"],
                raw_transcript=text_content,
            )
            routing_info["p08_next_action"] = result.next_action

            # #17 — Folgefrage / Abschluss-Nachricht an den Kunden zurücksenden.
            # Fail-open: Send-Fehler darf den Chunk-Return NICHT kaputtmachen.
            # E2: nur type(exc).__name__ loggen, nie str(exc).
            chat_id = _resolve_chat_id(tenant_id)
            if chat_id is not None and result.message:
                try:
                    from api.telegram import (  # Lazy-Import wie scheduler.py:104
                        _interview_cancel_keyboard,
                        _send_telegram_message,
                    )

                    # C5: Solange das Gespräch weiterläuft, hängt an der Frage ein
                    # sichtbarer Ausgang. An der Abschluss-Nachricht nicht — dann
                    # ist die Session ohnehin zu.
                    if result.is_closed:
                        sent = _send_telegram_message(chat_id, result.message, tenant_id=tenant_id)
                    else:
                        sent = _send_telegram_message(
                            chat_id,
                            result.message,
                            tenant_id=tenant_id,
                            reply_markup=_interview_cancel_keyboard(),
                        )
                    routing_info["p08_message_sent"] = sent
                    if not sent:
                        logger.warning(
                            "telegram_task: p08-Folgefrage konnte nicht an chat …%s gesendet werden"
                            " (tenant=%s)",
                            str(chat_id)[-4:],
                            tenant_id,
                        )
                except Exception as exc:
                    logger.warning("p08 message send failed: %s", type(exc).__name__)
                    routing_info["p08_message_sent"] = False
            else:
                routing_info["p08_message_sent"] = False

            # #19 — Session-Close → Post-Generierung asynchron triggern.
            # Reihenfolge: erst Abschluss-Text (#17, oben), dann generierter
            # Post (zweite Nachricht, aus session_post_task). Nur ein ECHTER
            # active→closed-Übergang triggert (was_already_closed=False),
            # damit Spät-/Doppel-Events auf eine geschlossene Session P12 nicht
            # erneut feuern. Enqueue fail-open: ein Broker-/Enqueue-Fehler darf
            # den Routing-Return NICHT kaputtmachen. E2: nur Exception-Typ.
            if result.is_closed and not getattr(result, "was_already_closed", False):
                try:
                    from tasks.session_post_task import generate_post_from_session

                    generate_post_from_session.apply_async(
                        args=[str(decision.payload["session_id"]), tenant_id]
                    )
                    routing_info["post_generation_enqueued"] = True
                except Exception as exc:
                    logger.warning("post generation enqueue failed: %s", type(exc).__name__)
                    routing_info["post_generation_enqueued"] = False

        return routing_info
    except Exception as exc:
        # E2: nur Exception-Typ loggen, nie str(exc) — könnte Prompt-/PII-Fragmente tragen.
        logger.warning("inbound routing failed: %s", type(exc).__name__)
        return None


def _telegram_get_file(file_id: str, tenant_id: str) -> bytes | None:
    """Lädt Audio/Photo-Bytes vom Telegram-Server via per-Tenant-Bot-Token.

    Telegram-API: getFile(file_id) → file_path → GET file_path.
    Token wird NIEMALS geloggt (E2/D3).

    Args:
        file_id:   Telegram file_id aus dem Update-Payload.
        tenant_id: Tenant-ID zum Token-Lookup via get_tenant_bot_token.
    """
    from services.telegram_token_resolver import get_tenant_bot_token

    token = get_tenant_bot_token(tenant_id)
    if not token:
        logger.warning(
            "_telegram_get_file: kein aktiver Bot-Token für tenant %s — getFile skipped",
            tenant_id,
        )
        return None
    try:
        with httpx.Client(timeout=20) as client:
            r = client.get(f"{TELEGRAM_API_BASE}/bot{token}/getFile", params={"file_id": file_id})
            if r.status_code != 200:
                logger.warning("getFile %s → HTTP %s", file_id[:20], r.status_code)
                return None
            file_path = (r.json().get("result") or {}).get("file_path")
            if not file_path:
                logger.warning("getFile %s lieferte kein file_path", file_id[:20])
                return None
            r2 = client.get(f"{TELEGRAM_API_BASE}/file/bot{token}/{file_path}")
            if r2.status_code != 200:
                logger.warning("download %s → HTTP %s", file_path[:30], r2.status_code)
                return None
            return r2.content
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning("Telegram-getFile-Network-Error: %s", type(exc).__name__)
        return None


# ── async helpers ───────────────────────────────────────────────────────


async def _store_chunk_async(
    tenant_id: str,
    source_type: str,
    content_text: str,
    log_id: str,
    metadata: dict,
) -> str | None:
    """Async-Wrapper: chunkt Text via chunker, persistiert alle Chunks.

    Returns die ID des ersten Chunks (fuer Rueckwaertskompatibilitaet).
    Bei mehreren Chunks werden prev/next-Links via store_chunks_multi gesetzt.
    """
    from services.chunker import chunk_text
    from services.embedding_service import store_chunk, store_chunks_multi

    chunks = chunk_text(content_text, source_type)
    if not chunks:
        # Fallback: direkt speichern ohne Chunking (z.B. text zu kurz)
        # store_chunk wirft ValueError fuer leere Texte — defensiv zurueck
        logger.warning(
            "_store_chunk_async: chunker lieferte 0 Chunks fuer source_type=%s, len=%d — direkt speichern",
            source_type,
            len(content_text),
        )
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with SessionMaker() as db:
                return await store_chunk(
                    db=db,
                    tenant_id=tenant_id,
                    source_type=source_type,
                    content_text=content_text,
                    source_ref=f"telegram_message_log:{log_id}",
                    metadata=metadata,
                    classify=True,
                )
        finally:
            await engine.dispose()

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with SessionMaker() as db:
            ids = await store_chunks_multi(
                db,
                tenant_id=tenant_id,
                source_type=source_type,
                chunks=chunks,
                source_ref=f"telegram_message_log:{log_id}",
                base_metadata=metadata,
                classify=True,
            )
        return ids[0] if ids else None
    finally:
        await engine.dispose()


# ── celery task ─────────────────────────────────────────────────────────


@celery_app.task(name="tasks.telegram_task.process_telegram_update", bind=True, max_retries=1)
def process_telegram_update(self, log_id: str) -> dict:
    """Verarbeitet eine telegram_message_log-Zeile.

    Returns dict mit Statusinfo. Idempotent: wenn transcript_text
    schon gesetzt, wird kein erneuter Transcribe-Call gemacht.
    """
    row = _load_log_row(log_id)
    if row is None:
        logger.warning("telegram_task: log_id=%s nicht gefunden", log_id)
        return {"status": "skipped", "reason": "log_not_found"}

    if row["transcript_text"]:
        logger.info("telegram_task: log_id=%s schon transkribiert — skip", log_id)
        return {"status": "already_processed"}

    tenant_id = row["tenant_id"]
    payload = row["original_payload"]
    message_type = row["message_type"]

    if message_type == "voice":
        return _process_voice(log_id, tenant_id, payload)
    elif message_type == "photo":
        return _process_photo(log_id, tenant_id, payload)
    else:
        return _process_text(log_id, tenant_id, payload)


def _process_voice(log_id: str, tenant_id: str, payload: dict) -> dict:
    voice_obj: dict = payload.get("voice") or {}
    file_id = voice_obj.get("file_id")
    duration = int(voice_obj.get("duration") or 0)
    mime_type = voice_obj.get("mime_type") or "audio/ogg"

    if not file_id:
        logger.warning("voice ohne file_id, log_id=%s", log_id)
        return {"status": "error", "reason": "no_file_id"}

    audio_bytes = _telegram_get_file(file_id, tenant_id)
    if not audio_bytes:
        return {"status": "error", "reason": "download_failed"}

    try:
        result: TranscriptionResult = transcribe_voice(
            audio_bytes,
            mime_type=mime_type,
            language_hint="de",
            tenant_id=tenant_id,
        )
    except TranscriptionError as exc:
        logger.warning("transcribe_voice fail: %s", exc)
        return {"status": "error", "reason": str(exc)[:80]}

    transcript = (result.text or "").strip()
    if not transcript:
        return {"status": "error", "reason": "empty_transcript"}

    _update_log_transcript(log_id, transcript, result.model_id or "unknown", result.confidence)

    channel = payload.get("_channel") or "telegram"
    source_type = "voice_whatsapp" if channel == "whatsapp" else "voice_telegram"
    chunk_metadata = {
        "telegram_message_id": payload.get("message_id") or payload.get("id"),
        "duration_sec": duration,
        "transcription_confidence": round(min(max(result.confidence, 0), 1), 2),
        "transcription_model": result.model_id,
        "channel": channel,
    }
    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, source_type, transcript, log_id, chunk_metadata)
        )
    except Exception as exc:
        logger.warning("store_voice_chunk failed: %s", exc)
        return {"status": "transcribed_no_chunk", "reason": str(exc)[:120]}

    chat_id_voice = (payload.get("chat") or {}).get("id")
    result_dict = {
        "status": "ok",
        "transcript_chars": len(transcript),
        "memory_chunk_id": chunk_id,
        "source_type": source_type,
        "channel": channel,
    }

    # PR 2 — Weiche VOR dem Routing: greift sie, entscheidet der Nutzer per Button
    # und es läuft kein LLM-Rateschritt. Nur für Telegram: die Buttons sind ein
    # Inline-Keyboard, das der WhatsApp-Adapter nicht kennt.
    if channel == "telegram" and _awaits_user_choice(tenant_id, transcript):
        # Fallback auf den Tenant-Chat: fehlt „chat" im Payload, wäre die Nachricht
        # sonst ohne jede Reaktion zu Ende — der Zustand, den diese PR beseitigt.
        target_chat = chat_id_voice or _resolve_chat_id(tenant_id)
        result_dict["routed_to"] = "awaiting_user_choice"
        result_dict["choice_prompt_sent"] = bool(target_chat) and _send_choice_prompt(
            tenant_id, target_chat, log_id, transcript, "🎤"
        )
        return result_dict

    # Bestätigung an den Nutzer senden
    if chat_id_voice and channel == "telegram":
        preview = transcript[:80].rstrip()
        suffix = "…" if len(transcript) > 80 else ""
        try:
            from api.telegram import _send_telegram_message

            _send_telegram_message(
                chat_id_voice,
                f"🎤 Gespeichert: „{preview}{suffix}“",
                tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.warning("voice confirmation send failed: %s", type(exc).__name__)

    routing_info = _route_inbound_message(tenant_id, transcript, log_id=log_id)
    if routing_info:
        result_dict.update(routing_info)
    return result_dict


def _process_photo(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Photo-Pipeline (Welle 4): getFile → OCR (+Vision-Stub) → memory_chunk."""
    photos = payload.get("photo") or []
    if not photos:
        return {"status": "skipped", "reason": "no_photo_array"}
    # Telegram liefert Liste verschiedener Auflösungen — nimm die größte
    best = max(photos, key=lambda p: p.get("file_size") or 0)
    file_id = best.get("file_id")
    if not file_id:
        return {"status": "error", "reason": "no_file_id"}

    image_bytes = _telegram_get_file(file_id, tenant_id)
    if not image_bytes:
        return {"status": "error", "reason": "download_failed"}

    from services.photo_pipeline import PhotoProcessingError, process_photo

    caption = (payload.get("caption") or "").strip() or None
    try:
        result = asyncio.run(process_photo(image_bytes, hint=caption))
    except PhotoProcessingError as exc:
        logger.warning("photo pipeline fail: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}
    except Exception as exc:
        logger.warning("photo pipeline unexpected: %s", exc)
        return {"status": "error", "reason": "pipeline_exception"}

    content_text = result["content_text"]
    if caption:
        content_text = f"{caption}\n\n{content_text}"

    channel = payload.get("_channel") or "telegram"
    source_type = "photo_whatsapp" if channel == "whatsapp" else "photo_telegram"
    chunk_metadata = {
        "telegram_message_id": payload.get("message_id") or payload.get("id"),
        "file_size": best.get("file_size"),
        "width": best.get("width"),
        "height": best.get("height"),
        "ocr_chars": result.get("ocr_chars", 0),
        "ocr_lang": result.get("ocr_lang"),
        "has_description": bool(result.get("description")),
        "caption": caption,
        "channel": channel,
    }

    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, source_type, content_text, log_id, chunk_metadata)
        )
    except Exception as exc:
        logger.warning("store_photo_chunk failed: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}

    return {
        "status": "ok",
        "memory_chunk_id": chunk_id,
        "ocr_chars": result.get("ocr_chars", 0),
        "source_type": source_type,
        "channel": channel,
    }


def _process_photo_stub(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Backwards-Compat-Wrapper, falls noch ein älterer Pfad ihn aufruft."""
    return _process_photo(log_id, tenant_id, payload)


def _process_text(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Text-Nachrichten — speichern als manual_note (kein Wizard-Bridge in dieser Welle).

    Akzeptiert beide Payload-Formate:
    - Telegram:  message["text"] = "..."
    - WhatsApp:  message["text"] = {"body": "..."}
    """
    raw = payload.get("text")
    if isinstance(raw, dict):
        text_content = (raw.get("body") or "").strip()
    elif isinstance(raw, str):
        text_content = raw.strip()
    else:
        text_content = ""
    if not text_content:
        return {"status": "skipped", "reason": "empty_text"}
    if len(text_content) < 10:
        # #36 S4 Kurztext-Bypass: „2" als Varianten-Wahl hat len<10 und würde
        # hier normalerweise gestoppt. Wenn ein Pending-Marker existiert und
        # der Text ein gültiges Choice-Token ist, durchlassen.
        # Billig: 1 tenant-scoped SELECT nur wenn Pending-Marker vorhanden;
        # ohne Treffer → too_short wie bisher.
        try:
            from tasks.p13_variants_task import _try_p13_variant_choice

            choice_result = _try_p13_variant_choice(tenant_id, text_content)
            if choice_result and isinstance(choice_result, dict):
                return {"status": "ok", **choice_result}
        except Exception:
            pass  # fail-open: too_short wie bisher
        return {"status": "skipped", "reason": "too_short"}

    # channel-Erkennung: WhatsApp-Adapter schreibt _channel='whatsapp' ins payload
    channel = payload.get("_channel") or "telegram"
    chunk_metadata = {
        "telegram_message_id": payload.get("message_id") or payload.get("id"),
        "channel": channel,
    }
    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, "manual_note", text_content, log_id, chunk_metadata)
        )
    except Exception as exc:
        logger.warning("store_text_chunk failed: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}

    result_dict = {
        "status": "ok",
        "memory_chunk_id": chunk_id,
        "source_type": "manual_note",
        "channel": channel,
    }
    chat_id = (payload.get("chat") or {}).get("id")

    # PR 2 — dieselbe Weiche wie im Voice-Pfad (Louis, 30.07.: Text-Parität).
    if channel == "telegram" and _awaits_user_choice(tenant_id, text_content):
        target_chat = chat_id or _resolve_chat_id(tenant_id)
        result_dict["routed_to"] = "awaiting_user_choice"
        result_dict["choice_prompt_sent"] = bool(target_chat) and _send_choice_prompt(
            tenant_id, target_chat, log_id, text_content, "📝"
        )
        return result_dict

    routing_info = _route_inbound_message(tenant_id, text_content, log_id=log_id)
    if routing_info:
        result_dict.update(routing_info)
    elif channel == "telegram" and chat_id:
        # Kein Routing-Gate hat gegriffen → Memory-Default → Bestätigung senden
        try:
            from api.telegram import _send_telegram_message

            _send_telegram_message(
                chat_id,
                "✅ Gespeichert im Gedächtnis.",
                tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.warning("text confirmation send failed: %s", type(exc).__name__)
    return result_dict
