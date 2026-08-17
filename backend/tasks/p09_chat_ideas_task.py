# AUDITED-2026-08-17 (zubu-louis-dialog): RLS-Tiefen-Audit, Datei vollstaendig gelesen, alle sync_session_factory-Bloecke geurteilt.
"""P09-Task: Top-5 bestehende Content-Ideen in den Chat liefern (Issue #36 S2).

Wird von tasks.telegram_task._route_inbound_message per Celery enqueued,
wenn die P09-Heuristik (is_idea_request) im No-Session-Zweig anschlägt.

Datenfluss
----------
1. Top-5-Ideen laden (tenant-scoped, E3): content_ideas WHERE status='new'
   ORDER BY relevance_score DESC, created_at DESC LIMIT 5.
   Optional Topic-Filter via extract_topic() (ILIKE, kein LLM).
2. Ideen vorhanden → Chat-Nachricht (Top-5-Format, max. 4000 Zeichen).
3. Keine Ideen → On-demand-Ideation NUR bei positivem Cost-Cap-Vorcheck:
   jüngstes analysiertes SourceItem ohne eigene Ideen →
   auto_generate_ideas via run_inline() in-process → Schritt 1 wiederholen.
   Kein analysiertes Item → freundliche Notiz.
   Cap erschöpft → Kosten-Notiz statt Ideation (wie post_feedback_task.py:368-381).

Fail-open & Schicht-3
---------------------
* Kein Raise, nur Status-Dicts (Muster post_feedback_task.py).
* E2: Logs nur IDs/Counts/Typen, nie Ideen-Titel/-Hooks im Log.
* E3: Jede Query trägt tenant_id im WHERE.
* Idempotenz: Task ist read-mostly; Doppellauf = doppelte Chat-Nachricht, kein
  State-Schaden. Der Upstream-Dedup-Guard (routed_to via telegram_task:190-203)
  verhindert Celery-Retry-Doppelläufe.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import text

from models.base import sync_session_factory
from services.rls import set_rls_tenant_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_TELEGRAM_MAX_CHARS = 4000
_COST_CAP_USD = float(os.environ.get("COST_CAP_USD_PER_DAY", "5.0"))
_TOP_N = 5


@celery_app.task(
    name="tasks.p09_chat_ideas_task.deliver_ideas_to_chat",
    bind=True,
    max_retries=1,
)
def deliver_ideas_to_chat(
    self,
    tenant_id: str,
    trigger_text: str,
    log_id: str | None = None,
) -> dict:
    """Liefert die Top-5 Content-Ideen des Tenants in den Chat.

    Args:
        tenant_id:    Tenant (E3-Scope + chat_id-Auflösung).
        trigger_text: Originaltext der Ideen-Anfrage (max. 500 Zeichen, defensiv gekappt).
                      Wird für extract_topic() genutzt — kein LLM, kein Log.
        log_id:       telegram_message_log.id (für Debug, nicht für Idempotenz-Gate
                      — der upstream-Dedup-Guard in telegram_task übernimmt das).

    Returns ein Status-Dict. Fail-open: kein Raise.
    """
    # Defensiv kappen (E2: nie Roh-Text in LLM-Calls oder Logs weitergeben)
    trigger_text = (trigger_text or "")[:500]

    # 1. Optionales Topic aus dem Trigger-Text (dep-frei, kein LLM)
    try:
        from services.chat_intent_heuristics import extract_topic

        topic_kw = extract_topic(trigger_text)
    except Exception as exc:
        logger.warning("p09_task: extract_topic failed: %s", type(exc).__name__)
        topic_kw = None

    # 2. Top-5 Ideen laden (tenant-scoped, E3)
    ideas = _load_top_ideas(tenant_id, topic_kw=topic_kw, limit=_TOP_N)

    if not ideas:
        # Keine Ideen vorhanden → On-demand-Generierung mit Cost-Cap-Vorcheck
        return _generate_on_demand(tenant_id, log_id=log_id)

    # 3. Chat-Nachricht zusammenbauen und senden
    return _send_ideas_message(tenant_id, ideas)


# ---------------------------------------------------------------------------
# Interne Helfer
# ---------------------------------------------------------------------------


def _load_top_ideas(tenant_id: str, topic_kw: str | None, limit: int) -> list[dict]:
    """Lädt die Top-N Ideen des Tenants aus content_ideas (E3-scoped).

    Bei topic_kw: Title ILIKE '%kw%' OR description ILIKE '%kw%' als Filter.
    Fallback auf alle Ideen (kein Topic-Filter), wenn gefiltertes Ergebnis leer.
    """
    try:
        with sync_session_factory() as db:
            # tenant-gescopet: tenant_id ist Funktionsparameter.
            set_rls_tenant_sync(db, tenant_id)
            params: dict = {"tid": tenant_id, "limit": limit}
            if topic_kw:
                params["kw"] = f"%{topic_kw}%"
                sql = text(
                    "SELECT id, title, hook_suggestion, relevance_score "
                    "FROM content_ideas "
                    "WHERE tenant_id = :tid AND status = 'new' "
                    "  AND (title ILIKE :kw OR description ILIKE :kw) "
                    "ORDER BY relevance_score DESC NULLS LAST, created_at DESC "
                    "LIMIT :limit"
                )
                rows = db.execute(sql, params).fetchall()
                if rows:
                    return [_row_to_dict(r) for r in rows]
                # Kein Topic-Treffer → Fallback ohne Filter
            sql_all = text(
                "SELECT id, title, hook_suggestion, relevance_score "
                "FROM content_ideas "
                "WHERE tenant_id = :tid AND status = 'new' "
                "ORDER BY relevance_score DESC NULLS LAST, created_at DESC "
                "LIMIT :limit"
            )
            rows = db.execute(sql_all, {"tid": tenant_id, "limit": limit}).fetchall()
            return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        logger.warning("p09_task: load_top_ideas failed: %s", type(exc).__name__)
        return []


def _row_to_dict(row) -> dict:
    return {
        "id": str(row.id),
        "title": row.title or "",
        "hook_suggestion": row.hook_suggestion or "",
        "relevance_score": row.relevance_score,
    }


def _check_cost_cap(tenant_id: str) -> bool:
    """Gibt True zurück wenn Budget noch vorhanden (< Cap), False bei Überschreitung.

    Muster: layer1_extraction.py:241-273. Fail-open: True bei DB-Fehler (kein Blocken).
    """
    try:
        from datetime import date

        with sync_session_factory() as db:
            # tenant-gescopet: tenant_id ist Funktionsparameter.
            set_rls_tenant_sync(db, tenant_id)
            row = db.execute(
                text(
                    "SELECT cost_usd FROM daily_cost_tenant "
                    "WHERE tenant_id = :tid AND date = :date"
                ),
                {"tid": tenant_id, "date": date.today().isoformat()},
            ).fetchone()
            if row and float(row[0]) >= _COST_CAP_USD:
                logger.warning(
                    "p09_task: cost cap reached for tenant=%s (%.4f >= %.4f)",
                    tenant_id,
                    float(row[0]),
                    _COST_CAP_USD,
                )
                return False
        return True
    except Exception as exc:
        logger.warning("p09_task: cost_cap check failed (fail-open): %s", type(exc).__name__)
        return True  # fail-open: lieber generieren als blockieren


def _generate_on_demand(tenant_id: str, log_id: str | None) -> dict:
    """Löst On-demand-Ideation aus (6–9 LLM-Calls!) — nur bei Budget-OK.

    Muster: api/ideas.py:116-213 (Dashboard-Trigger), auto_generate_ideas-Task.
    """
    # Cost-Cap-Vorcheck (Pflicht — auto_generate_ideas kostet 6–9 LLM-Calls!)
    if not _check_cost_cap(tenant_id):
        _send_cost_notice(tenant_id)
        return {"status": "skipped", "reason": "paused_for_cost"}

    # Jüngstes analysiertes SourceItem ohne eigene Ideen laden (tenant-scoped, E3)
    item_id = _find_best_source_item(tenant_id)
    if not item_id:
        _send_no_sources_notice(tenant_id)
        return {"status": "skipped", "reason": "no_source_item"}

    # auto_generate_ideas in-process. `timeout=120` stand hier bis 06.08.2026 und
    # war wirkungslos: `EagerResult.get()` wertet ihn nicht aus, die Task ist beim
    # Aufruf laengst gelaufen. Wer eine Zeitgrenze braucht, setzt sie in der Task.
    try:
        from services.celery_inline import run_inline
        from tasks.ideation_task import auto_generate_ideas

        result = run_inline(auto_generate_ideas, args=[item_id])
        if isinstance(result, dict) and result.get("status") not in ("ok", "already_exists"):
            logger.info("p09_task: ideation not ok: %s", result.get("status"))
            return {"status": "skipped", "reason": "ideation_failed"}
    except Exception as exc:
        logger.warning("p09_task: ideation apply failed: %s", type(exc).__name__)
        return {"status": "error", "reason": "ideation_exception"}

    # Ideen erneut laden
    ideas = _load_top_ideas(tenant_id, topic_kw=None, limit=_TOP_N)
    if not ideas:
        return {"status": "skipped", "reason": "no_ideas_after_ideation"}

    return _send_ideas_message(tenant_id, ideas)


def _find_best_source_item(tenant_id: str) -> str | None:
    """Findet das jüngste analysierte SourceItem ohne eigene Ideen (E3).

    'Analysiert' bedeutet: analysis IS NOT NULL (hat Transkript/Analyse-Daten).
    """
    try:
        with sync_session_factory() as db:
            # tenant-gescopet: tenant_id ist Funktionsparameter.
            set_rls_tenant_sync(db, tenant_id)
            row = db.execute(
                text(
                    "SELECT si.id FROM source_items si "
                    "WHERE si.tenant_id = :tid "
                    "  AND si.analysis IS NOT NULL "
                    "  AND NOT EXISTS ("
                    "    SELECT 1 FROM content_ideas ci "
                    "    WHERE ci.source_item_id = si.id AND ci.tenant_id = :tid"
                    "  ) "
                    "ORDER BY si.created_at DESC LIMIT 1"
                ),
                {"tid": tenant_id},
            ).fetchone()
            if row:
                return str(row.id)
        return None
    except Exception as exc:
        logger.warning("p09_task: find_source_item failed: %s", type(exc).__name__)
        return None


def _send_ideas_message(tenant_id: str, ideas: list[dict]) -> dict:
    """Formatiert die Top-5-Ideen und sendet sie in den Chat (fail-open)."""
    lines = ["Hier sind deine Top-5 Post-Ideen:"]
    for i, idea in enumerate(ideas, 1):
        title = (idea.get("title") or "").strip()
        hook = (idea.get("hook_suggestion") or "").strip()[:120]
        if hook:
            lines.append(f"{i}. {title} — 💡 {hook}")
        else:
            lines.append(f"{i}. {title}")
    lines.append(
        "\nGefällt dir eine? Erzähl mir kurz deine Sicht dazu — oder schick mir deine eigene Idee."
    )

    message = "\n".join(lines)
    if len(message) > _TELEGRAM_MAX_CHARS:
        message = message[:_TELEGRAM_MAX_CHARS]

    chat_id = _resolve_chat_id(tenant_id)
    if chat_id is None:
        logger.info("p09_task: no active chat link for tenant — ideas not sent")
        return {
            "status": "ok",
            "sent": False,
            "reason": "no_chat_link",
            "ideas_count": len(ideas),
        }

    try:
        from api.telegram import _send_telegram_message

        _send_telegram_message(chat_id, message, tenant_id=tenant_id)
        return {"status": "ok", "sent": True, "ideas_count": len(ideas)}
    except Exception as exc:
        logger.warning("p09_task: telegram send failed: %s", type(exc).__name__)
        return {
            "status": "ok",
            "sent": False,
            "reason": "send_failed",
            "ideas_count": len(ideas),
        }


def _resolve_chat_id(tenant_id: str) -> int | None:
    """Lookup active Telegram chat_id (wiederverwendet Muster telegram_task.py:107-128).

    Fail-open: None bei Fehler oder kein aktiver Link.
    """
    try:
        from tasks.telegram_task import _resolve_chat_id as _resolve

        return _resolve(tenant_id)
    except Exception as exc:
        logger.warning("p09_task: chat_id resolve failed: %s", type(exc).__name__)
        return None


def _send_cost_notice(tenant_id: str) -> None:
    """Sendet freundliche Kosten-Notiz in den Chat (Muster post_feedback_task.py:368-381)."""
    try:
        chat_id = _resolve_chat_id(tenant_id)
        if chat_id is None:
            return
        from api.telegram import _send_telegram_message

        _send_telegram_message(
            chat_id,
            "Das Tageslimit ist leider erreicht — morgen geht's weiter!",
            tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.warning("p09_task: cost notice send failed: %s", type(exc).__name__)


def _send_no_sources_notice(tenant_id: str) -> None:
    """Sendet freundliche Notiz wenn keine analysierten Quellen vorhanden."""
    try:
        chat_id = _resolve_chat_id(tenant_id)
        if chat_id is None:
            return
        from api.telegram import _send_telegram_message

        _send_telegram_message(
            chat_id,
            "Noch keine analysierten Quellen — füge im Dashboard eine Quelle hinzu "
            "oder erzähl mir deine eigene Idee.",
            tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.warning("p09_task: no-sources notice send failed: %s", type(exc).__name__)
