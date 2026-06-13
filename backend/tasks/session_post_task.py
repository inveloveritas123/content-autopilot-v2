"""Session-Close → Post-Generierung (Issue #19, [BLOCKER], M24 / Board 5.5).

Wird von tasks.telegram_task._route_inbound_message beim ECHTEN Session-Close
(active→closed) per Celery enqueued. Fährt P12→P12b aus den im bot_session
gesammelten Roh-Transkripten und sendet den fertigen Post als zweite Nachricht
in den Telegram-Chat des Tenants — „Kunde hat fertigen Text im Chat".

Datenfluss
----------
1. Idempotenz-Gate: existiert bereits ein content_piece für diese Session
   (content_metadata->>'bot_session_id'), → already_generated, kein zweiter Lauf.
2. Session laden (Tenant-Scope = E3-Mandantentrennung); status != 'closed' → skip.
3. Q/A-Paare aus messages[*] bauen (bot = Frage, user_transcript = Antwort).
   0 Paare (Alt-Session ohne Transkripte / leere Session) → skip (Kostenschutz).
4. Aktive Profile (voice/avatar) sync via services.canonical_profiles laden.
5. _run_p12_p12b_pipeline(tenant_id, idea_id=None, …) (idea_id nullable, B13).
6. Content-Piece markieren (bot_session_id) + _send_telegram_message(chat_id, post).

Fail-open & Schicht-3
---------------------
* Jeder Fehlerpfad gibt ein Status-Dict zurück, crasht NICHT (kein Telegram-
  Spam-Retry).
* Geflaggte Posts (Sensitive-Detector) gehen NICHT roh in den Chat — stattdessen
  Review-Hinweis (Review-Queue-Pfad von #83 bleibt intakt).
* Logs tragen NUR IDs/Typen, NIE Transkript-/Post-Fragmente (E2-Konvention).
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import text

from models.base import sync_session_factory
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Telegram-Hardlimit 4096 Zeichen — defensiv kappen.
_TELEGRAM_MAX_CHARS = 4000


def _build_qa_pairs(messages: list) -> list[dict]:
    """Baut Q/A-Paare aus bot_session.messages für den P12-Input.

    messages[i]["bot"]            = die vom Bot gestellte Frage
    messages[i]["user_transcript"] = die Roh-Antwort des Kunden (#19a)

    Jeder Eintrag mit nicht-leerem user_transcript wird zu einem Paar
    {"question_text": <bot-Frage>, "answer_text": <transkript>} (Format wie
    api.ideas._run_p12_p12b_pipeline erwartet). Einträge ohne Transkript
    (z.B. der Opener) werden übersprungen.
    """
    pairs: list[dict] = []
    if not isinstance(messages, list):
        return pairs
    for entry in messages:
        if not isinstance(entry, dict):
            continue
        answer = (entry.get("user_transcript") or "").strip()
        if not answer:
            continue
        question = (entry.get("bot") or "").strip()
        pairs.append({"question_text": question, "answer_text": answer})
    return pairs


@celery_app.task(
    name="tasks.session_post_task.generate_post_from_session",
    bind=True,
    max_retries=1,
)
def generate_post_from_session(self, session_id: str, tenant_id: str) -> dict:
    """Generiert beim Session-Close einen Post und sendet ihn in den Chat.

    Args:
        session_id: bot_session.id der geschlossenen Session.
        tenant_id:  Tenant (für E3-Scope + chat_id-Auflösung).

    Returns ein Status-Dict (für Tests/Observability). Fail-open: keine
    Exception verlässt diese Funktion.
    """
    # 1. Idempotenz-Gate (zuerst!) — existiert schon ein Piece für diese Session?
    try:
        with sync_session_factory() as db:
            existing = db.execute(
                text(
                    "SELECT 1 FROM content_pieces "
                    "WHERE tenant_id = :tid "
                    "      AND content_metadata->>'bot_session_id' = :sid LIMIT 1"
                ),
                {"tid": tenant_id, "sid": session_id},
            ).fetchone()
        if existing is not None:
            logger.info("session_post_task: session=%s already has a post — skip", session_id)
            return {"status": "already_generated"}
    except Exception as exc:
        logger.warning("session_post_task: idempotency gate failed: %s", type(exc).__name__)
        return {"status": "error", "reason": "idempotency_gate_failed"}

    # 2. Session laden (Tenant-Scope im WHERE = E3-Mandantentrennung)
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT messages, status, mode FROM bot_session "
                    "WHERE id = :id AND tenant_id = :tid LIMIT 1"
                ),
                {"id": session_id, "tid": tenant_id},
            ).fetchone()
    except Exception as exc:
        logger.warning("session_post_task: session load failed: %s", type(exc).__name__)
        return {"status": "error", "reason": "session_load_failed"}

    if row is None:
        return {"status": "skipped", "reason": "session_not_found"}

    messages_raw, status, _mode = row[0], row[1], row[2]
    if status != "closed":
        return {"status": "skipped", "reason": "session_not_closed"}

    messages_list = (
        json.loads(messages_raw) if isinstance(messages_raw, str) else (messages_raw or [])
    )

    # 3. Q/A-Paare bauen — 0 Paare → skip (Alt-Session ohne Transkripte / leer)
    answers_list = _build_qa_pairs(messages_list)
    if not answers_list:
        logger.info("session_post_task: session=%s has no answer transcripts — skip", session_id)
        return {"status": "skipped", "reason": "no_answers"}

    # 4. Aktive Profile (voice/avatar) sync laden (Fassade, Muster p12_task)
    voice_payload: dict = {}
    avatar_payload: dict = {}
    try:
        from services.canonical_profiles import load_active_profiles

        profiles = load_active_profiles(tenant_id)
        voice_payload = profiles.get("voice_profile", {}).get("payload") or {}
        avatar_payload = profiles.get("audience_avatar", {}).get("payload") or {}
    except Exception as exc:
        logger.warning(
            "session_post_task: profile load failed (continuing empty): %s",
            type(exc).__name__,
        )

    # 5. P12→P12b fahren — idea_id=None (nullable, B13). Lazy-Import wie
    #    tasks.backtest_task (vermeidet FastAPI-Importlast/Zyklus im Worker).
    try:
        from api.ideas import _run_p12_p12b_pipeline

        pipeline_result = _run_p12_p12b_pipeline(
            tenant_id, None, answers_list, voice_payload, avatar_payload
        )
    except Exception as exc:
        logger.warning("session_post_task: pipeline raised: %s", type(exc).__name__)
        return {"status": "error", "reason": "pipeline_exception"}

    if not isinstance(pipeline_result, dict) or pipeline_result.get("status") != "ok":
        reason = (
            pipeline_result.get("reason") or pipeline_result.get("status")
            if isinstance(pipeline_result, dict)
            else "unknown"
        )
        logger.info("session_post_task: pipeline not ok (reason=%s)", reason)
        return {"status": "error", "reason": reason}

    final_post = pipeline_result.get("final_post") or ""
    if not final_post:
        return {"status": "error", "reason": "empty_post"}

    p12_run_id = pipeline_result.get("p12_run_id")
    flagged = bool(pipeline_result.get("flagged_for_review"))

    # 6. Content-Piece markieren (bot_session_id) + P12b-Text übernehmen.
    #    Piece über p12_run_id finden (P12 hat es bereits angelegt). Fail-open.
    try:
        with sync_session_factory() as db:
            if p12_run_id:
                db.execute(
                    text(
                        "UPDATE content_pieces SET "
                        "content_text = :txt, "
                        "content_metadata = content_metadata || CAST(:meta AS jsonb) "
                        "WHERE tenant_id = :tid "
                        "      AND content_metadata->>'p12_run_id' = :rid"
                    ),
                    {
                        "txt": final_post,
                        "meta": json.dumps(
                            {"bot_session_id": session_id, "source": "bot_session_close"}
                        ),
                        "tid": tenant_id,
                        "rid": p12_run_id,
                    },
                )
                db.commit()
    except Exception as exc:
        logger.warning("session_post_task: piece marker update failed: %s", type(exc).__name__)

    # 7. Post in den Chat. Geflaggt → NICHT roh senden (Review-Queue-Pfad #83).
    chat_id = _resolve_chat_id(tenant_id)
    if chat_id is None:
        logger.info("session_post_task: no active chat link for tenant — post stored, not sent")
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
        logger.warning("session_post_task: telegram send failed: %s", type(exc).__name__)
        return {
            "status": "ok",
            "sent": False,
            "reason": "send_failed",
            "flagged_for_review": flagged,
            "p12_run_id": p12_run_id,
        }

    logger.info(
        "session_post_task: post delivered (session=%s kind=%s flagged=%s)",
        session_id,
        sent_kind,
        flagged,
    )
    return {
        "status": "ok",
        "sent": True,
        "sent_kind": sent_kind,
        "flagged_for_review": flagged,
        "p12_run_id": p12_run_id,
    }


def _resolve_chat_id(tenant_id: str) -> int | None:
    """Lookup active Telegram chat_id for a tenant (wiederverwendet #17-Helfer).

    Lazy-Import aus tasks.telegram_task, damit dieses Task-Modul keine
    Modul-Level-Abhängigkeit auf telegram_task (httpx/voice_transcription)
    aufbaut. Fail-open: None bei Fehler / kein aktiver Link.
    """
    try:
        from tasks.telegram_task import _resolve_chat_id as _resolve

        return _resolve(tenant_id)
    except Exception as exc:
        logger.warning("session_post_task: chat_id resolve failed: %s", type(exc).__name__)
        return None
