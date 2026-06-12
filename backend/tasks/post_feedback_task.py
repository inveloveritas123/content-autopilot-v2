"""Feedback-Regenerierungs-Task (Issue #37 — P16-Feedback-Loop „nochmal anders").

Wird von tasks.telegram_task._route_inbound_message per Celery enqueued, wenn
kein aktiver Session-Zustand vorliegt, aber ein letzter Bot-Post gefunden wird
und der Intent `post_feedback` erkannt wird.

Datenfluss
----------
1. Idempotenz-Gate: existiert bereits ein Piece mit feedback_source_log_id = log_id
   (tenant-scoped) → already_generated (Celery-Retry/Doppel-Webhook).
2. Original-Piece laden (tenant-scoped, E3): liefert content_text (Vorgänger-Post)
   + bot_session_id (Rückweg zum Transkript). Kein bot_session_id → skipped.
3. Loop-Limit prüfen (migrationsfrei): COUNT(content_pieces) je bot_session_id
   gegen TELEGRAM_FEEDBACK_MAX_ROUNDS (Env, Default 2). Limit → Limit-Notiz in Chat.
4. Zurück zum Transkript: bot_session.messages laden → _build_qa_pairs.
   0 Paare → skipped (Kostenschutz wie session_post_task.py:127-131).
5. Feedback-Injektion: answers_list um zwei Steering-Keys ergänzen —
   {"question_text": "_kundenfeedback_runde_N", "answer_text": <feedback_text>} und
   {"question_text": "_vorheriger_post", "answer_text": <Vorgänger-Post>}.
6. Profile laden → _run_p12_p12b_pipeline(tenant_id, None, answers_list, voice, avatar).
7. Kosten-Cap-Behandlung: paused_for_cost → Kosten-Notiz in Chat.
8. Neues Piece markieren (über p12_run_id):
   content_metadata || {"bot_session_id": …, "source": "post_feedback_regen",
   "feedback_round": N+1, "parent_post_id": post_id, "feedback_source_log_id": log_id}.
9. Senden: geflaggt → Review-Notiz (#83-Pfad intakt); Send-Fehler fail-open.

Fail-open & Schicht-3
---------------------
* Jeder Fehlerpfad gibt ein Status-Dict zurück, kein Raise (kein Telegram-Spam-Retry).
* Logs tragen NUR IDs/Typen/Counts, NIE Feedback-/Post-/Transkript-Fragmente (E2).
* Jede DB-Query ist tenant-scoped (E3-Mandantentrennung).

Muster: tasks/session_post_task.py (#19).
"""

from __future__ import annotations

import json
import logging
import os

from sqlalchemy import text

from models.base import sync_session_factory
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_TELEGRAM_MAX_CHARS = 4000
_FEEDBACK_MAX_ROUNDS = int(os.environ.get("TELEGRAM_FEEDBACK_MAX_ROUNDS", "2"))


@celery_app.task(
    name="tasks.post_feedback_task.regenerate_post_from_feedback",
    bind=True,
    max_retries=1,
)
def regenerate_post_from_feedback(
    self,
    post_id: str,
    tenant_id: str,
    feedback_text: str,
    log_id: str | None = None,
) -> dict:
    """Generiert nach Kunden-Feedback einen neuen Post und sendet ihn in den Chat.

    Args:
        post_id:       content_pieces.id des Vorgänger-Posts.
        tenant_id:     Tenant (E3-Scope + chat_id-Auflösung).
        feedback_text: Der Kunden-Feedback-Text (max. 1000 Zeichen, defensiv gekappt).
        log_id:        telegram_message_log.id für Idempotenz-Gate + Piece-Marker.

    Returns ein Status-Dict. Fail-open: keine Exception verlässt diese Funktion.
    """
    # Defensiv kappen — nie ungekappten Feedback-Text in Prompts/Logs (E2)
    feedback_text = (feedback_text or "")[:1000]

    # 1. Idempotenz-Gate (zuerst!) — existiert schon ein Piece für diesen log_id?
    if log_id is not None:
        try:
            with sync_session_factory() as db:
                existing = db.execute(
                    text(
                        "SELECT 1 FROM content_pieces "
                        "WHERE tenant_id = :tid "
                        "  AND content_metadata->>'feedback_source_log_id' = :lid LIMIT 1"
                    ),
                    {"tid": tenant_id, "lid": str(log_id)},
                ).fetchone()
            if existing is not None:
                logger.info(
                    "post_feedback_task: log_id=%s already has a regen piece — skip", log_id
                )
                return {"status": "already_generated"}
        except Exception as exc:
            logger.warning("post_feedback_task: idempotency gate failed: %s", type(exc).__name__)
            return {"status": "error", "reason": "idempotency_gate_failed"}

    # 2. Original-Piece laden (tenant-scoped, E3)
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT id, content_text, content_metadata->>'bot_session_id' AS bot_session_id "
                    "FROM content_pieces "
                    "WHERE id = :pid AND tenant_id = :tid LIMIT 1"
                ),
                {"pid": post_id, "tid": tenant_id},
            ).fetchone()
    except Exception as exc:
        logger.warning("post_feedback_task: piece load failed: %s", type(exc).__name__)
        return {"status": "error", "reason": "piece_load_failed"}

    if row is None:
        return {"status": "skipped", "reason": "piece_not_found"}

    predecessor_text = (row.content_text or "").strip()
    bot_session_id = row.bot_session_id

    if not bot_session_id:
        # Kein Transkript-Rückweg (z.B. Dashboard-Posts) → kein neuer Durchlauf
        logger.info("post_feedback_task: piece=%s has no bot_session_id — skip", post_id)
        return {"status": "skipped", "reason": "no_bot_session_id"}

    # 3. Loop-Limit prüfen (migrationsfrei, COUNT je bot_session_id, tenant-scoped, E3)
    try:
        with sync_session_factory() as db:
            count = db.execute(
                text(
                    "SELECT count(*) FROM content_pieces "
                    "WHERE tenant_id = :tid "
                    "  AND content_metadata->>'bot_session_id' = :sid"
                ),
                {"tid": tenant_id, "sid": str(bot_session_id)},
            ).scalar()
        count = int(count or 0)
    except Exception as exc:
        logger.warning("post_feedback_task: loop limit count failed: %s", type(exc).__name__)
        count = 0  # fail-open: kein Limit-Stopp bei Zähl-Fehler

    # count enthält das Original-Piece (#19) + alle Regen-Pieces.
    # rounds = count - 1: erstes Piece ist der Originalpost.
    rounds = max(count - 1, 0)
    if rounds >= _FEEDBACK_MAX_ROUNDS:
        logger.info(
            "post_feedback_task: loop limit reached (rounds=%d, max=%d) for session=%s",
            rounds,
            _FEEDBACK_MAX_ROUNDS,
            bot_session_id,
        )
        _send_limit_notice(tenant_id)
        return {"status": "skipped", "reason": "loop_limit"}

    # 4. Zurück zum Transkript: Session laden + Q/A-Paare bauen (tenant-scoped, E3)
    try:
        with sync_session_factory() as db:
            sess_row = db.execute(
                text(
                    "SELECT messages, status FROM bot_session "
                    "WHERE id = :sid AND tenant_id = :tid LIMIT 1"
                ),
                {"sid": str(bot_session_id), "tid": tenant_id},
            ).fetchone()
    except Exception as exc:
        logger.warning("post_feedback_task: session load failed: %s", type(exc).__name__)
        return {"status": "error", "reason": "session_load_failed"}

    if sess_row is None:
        return {"status": "skipped", "reason": "session_not_found"}

    messages_raw, _status = sess_row[0], sess_row[1]
    messages_list = (
        json.loads(messages_raw) if isinstance(messages_raw, str) else (messages_raw or [])
    )

    # Lazy-Import — vermeidet FastAPI-Importlast/Zyklen im Worker
    from tasks.session_post_task import _build_qa_pairs

    answers_list = _build_qa_pairs(messages_list)
    if not answers_list:
        logger.info(
            "post_feedback_task: session=%s has no answer transcripts — skip", bot_session_id
        )
        return {"status": "skipped", "reason": "no_answers"}

    # 5. Feedback-Injektion — Steering-Keys für P12-Context (Board-Schleife)
    # Runde N+1 = rounds + 1 (nach diesem Lauf)
    feedback_round = rounds + 1
    answers_list = list(answers_list)  # Kopie, um die Original-Liste nicht zu mutieren
    answers_list.append(
        {
            "question_text": f"_kundenfeedback_runde_{feedback_round}",
            "answer_text": feedback_text,
        }
    )
    answers_list.append(
        {
            "question_text": "_vorheriger_post",
            "answer_text": predecessor_text,
        }
    )

    # 6. Profile laden + P12→P12b fahren
    voice_payload: dict = {}
    avatar_payload: dict = {}
    try:
        from services.canonical_profiles import load_active_profiles

        profiles = load_active_profiles(tenant_id)
        voice_payload = profiles.get("voice_profile", {}).get("payload") or {}
        avatar_payload = profiles.get("audience_avatar", {}).get("payload") or {}
    except Exception as exc:
        logger.warning(
            "post_feedback_task: profile load failed (continuing empty): %s",
            type(exc).__name__,
        )

    try:
        from api.ideas import _run_p12_p12b_pipeline

        pipeline_result = _run_p12_p12b_pipeline(
            tenant_id, None, answers_list, voice_payload, avatar_payload
        )
    except Exception as exc:
        logger.warning("post_feedback_task: pipeline raised: %s", type(exc).__name__)
        return {"status": "error", "reason": "pipeline_exception"}

    if not isinstance(pipeline_result, dict) or pipeline_result.get("status") != "ok":
        reason = (
            pipeline_result.get("reason") or pipeline_result.get("status")
            if isinstance(pipeline_result, dict)
            else "unknown"
        )
        logger.info("post_feedback_task: pipeline not ok (reason=%s)", reason)

        # 7. Kosten-Cap-Behandlung: freundliche Notiz in den Chat
        if reason == "paused_for_cost":
            _send_cost_notice(tenant_id)
            return {"status": "skipped", "reason": "paused_for_cost"}
        return {"status": "error", "reason": reason}

    final_post = pipeline_result.get("final_post") or ""
    if not final_post:
        return {"status": "error", "reason": "empty_post"}

    p12_run_id = pipeline_result.get("p12_run_id")
    flagged = bool(pipeline_result.get("flagged_for_review"))

    # 8. Neues Piece markieren (bot_session_id + Feedback-Metadaten)
    try:
        with sync_session_factory() as db:
            if p12_run_id:
                meta = json.dumps(
                    {
                        "bot_session_id": str(bot_session_id),
                        "source": "post_feedback_regen",
                        "feedback_round": feedback_round,
                        "parent_post_id": str(post_id),
                        "feedback_source_log_id": str(log_id) if log_id else None,
                    }
                )
                db.execute(
                    text(
                        "UPDATE content_pieces SET "
                        "content_text = :txt, "
                        "content_metadata = content_metadata || CAST(:meta AS jsonb) "
                        "WHERE tenant_id = :tid "
                        "  AND content_metadata->>'p12_run_id' = :rid"
                    ),
                    {
                        "txt": final_post,
                        "meta": meta,
                        "tid": tenant_id,
                        "rid": p12_run_id,
                    },
                )
                db.commit()
    except Exception as exc:
        logger.warning("post_feedback_task: piece marker update failed: %s", type(exc).__name__)

    # 9. Post in den Chat senden
    chat_id = _resolve_chat_id(tenant_id)
    if chat_id is None:
        logger.info(
            "post_feedback_task: no active chat link for tenant — post stored, not sent"
        )
        return {
            "status": "ok",
            "sent": False,
            "reason": "no_chat_link",
            "flagged_for_review": flagged,
            "p12_run_id": p12_run_id,
        }

    try:
        from api.telegram import _send_telegram_message

        if flagged:
            _send_telegram_message(
                chat_id,
                "Dein Post ist fertig, wartet aber noch auf eine kurze Review.",
            )
            sent_kind = "review_notice"
        else:
            _send_telegram_message(chat_id, final_post[:_TELEGRAM_MAX_CHARS])
            sent_kind = "post"
    except Exception as exc:
        logger.warning("post_feedback_task: telegram send failed: %s", type(exc).__name__)
        return {
            "status": "ok",
            "sent": False,
            "reason": "send_failed",
            "flagged_for_review": flagged,
            "p12_run_id": p12_run_id,
        }

    logger.info(
        "post_feedback_task: post delivered (session=%s round=%d kind=%s flagged=%s)",
        bot_session_id,
        feedback_round,
        sent_kind,
        flagged,
    )
    return {
        "status": "ok",
        "sent": True,
        "sent_kind": sent_kind,
        "flagged_for_review": flagged,
        "p12_run_id": p12_run_id,
        "feedback_round": feedback_round,
    }


# ---------------------------------------------------------------------------
# Interne Helfer
# ---------------------------------------------------------------------------


def _resolve_chat_id(tenant_id: str) -> int | None:
    """Lookup active Telegram chat_id für einen Tenant (wiederverwendet #17-Helfer).

    Lazy-Import aus tasks.telegram_task. Fail-open: None bei Fehler.
    """
    try:
        from tasks.telegram_task import _resolve_chat_id as _resolve

        return _resolve(tenant_id)
    except Exception as exc:
        logger.warning("post_feedback_task: chat_id resolve failed: %s", type(exc).__name__)
        return None


def _send_limit_notice(tenant_id: str) -> None:
    """Sendet eine freundliche Limit-Nachricht in den Chat (fail-open)."""
    try:
        chat_id = _resolve_chat_id(tenant_id)
        if chat_id is None:
            return
        from api.telegram import _send_telegram_message

        _send_telegram_message(
            chat_id,
            "Du hast das maximale Feedback-Limit für diesen Post erreicht. "
            "Wenn du einen ganz neuen Post möchtest, starte einfach eine neue Session.",
        )
    except Exception as exc:
        logger.warning(
            "post_feedback_task: limit notice send failed: %s", type(exc).__name__
        )


def _send_cost_notice(tenant_id: str) -> None:
    """Sendet eine freundliche Kosten-Notiz in den Chat (fail-open)."""
    try:
        chat_id = _resolve_chat_id(tenant_id)
        if chat_id is None:
            return
        from api.telegram import _send_telegram_message

        _send_telegram_message(
            chat_id,
            "Das Tageslimit ist leider erreicht — morgen geht's weiter!",
        )
    except Exception as exc:
        logger.warning(
            "post_feedback_task: cost notice send failed: %s", type(exc).__name__
        )
