"""P13-Task: Eigene Idee → 3 Aufhänger-Varianten in den Chat (Issue #36 S3).

Wird von tasks.telegram_task._route_inbound_message per Celery enqueued,
wenn Gate 6 (Own-Idea-Vorfilter + Layer1 → spontaneous_idea ohne Session)
anschlägt.

Datenfluss
----------
1. Idempotenz-Gate: source_context->>'source_log_id' = :log_id → already_generated.
2. Cost-Cap-Vorcheck (generate_variants hat KEINEN eigenen Cap, p12_variants_task.py:91).
3. Manuelle Idee anlegen (sync-SQL-Spiegel von api/ideas.py:1294-1335):
   find-or-create Source type='manual' → Stub-SourceItem → content_ideas-INSERT.
   State-Marker chat_variant_choice_pending=true in source_context (JSONB, migrationsfrei).
4. Varianten generieren: generate_variants.apply(args=[idea_id]).get() in-process.
5. Varianten in den Chat: hook→1, story→2, these→3 (Reihenfolge wie api/ideas.py:1386).
   Fehler / no_valid_variants → Marker entfernen + Notiz.

Fail-open & Schicht-3
---------------------
* Kein Raise, nur Status-Dicts (Muster post_feedback_task.py).
* E2: Logs nur IDs/Counts/Typen, nie Idee-/Varianten-Text im Log.
* E3: Jede Query trägt tenant_id im WHERE.
* Idee-Text vor Persist auf 1000 Zeichen kappen (Muster post_feedback_task.py:76).
"""

from __future__ import annotations

import json
import logging
import os
import uuid

from sqlalchemy import text

from models.base import sync_session_factory
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_TELEGRAM_MAX_CHARS = 4000
_COST_CAP_USD = float(os.environ.get("COST_CAP_USD_PER_DAY", "5.0"))
_P13_CHOICE_WINDOW_HOURS = int(os.environ.get("TELEGRAM_P13_CHOICE_WINDOW_HOURS", "24"))


@celery_app.task(
    name="tasks.p13_variants_task.generate_variants_for_chat",
    bind=True,
    max_retries=1,
)
def generate_variants_for_chat(
    self,
    tenant_id: str,
    idea_text: str,
    log_id: str | None = None,
) -> dict:
    """Legt manuelle Idee an, generiert 3 Aufhänger und sendet sie in den Chat.

    Args:
        tenant_id:  Tenant (E3-Scope + chat_id-Auflösung).
        idea_text:  Roh-Text der Idee (max. 1000 Zeichen, defensiv gekappt).
        log_id:     telegram_message_log.id (für Idempotenz-Gate + Marker).

    Returns ein Status-Dict. Fail-open: kein Raise.
    """
    # Defensiv kappen (E2: nie Roh-Text unkontrolliert weitergeben)
    idea_text = (idea_text or "")[:1000]

    # 1. Idempotenz-Gate via source_log_id (Muster post_feedback_task.py:78-97)
    if log_id is not None:
        try:
            with sync_session_factory() as db:
                existing = db.execute(
                    text(
                        "SELECT 1 FROM content_ideas "
                        "WHERE tenant_id = :tid "
                        "  AND source_context->>'source_log_id' = :lid LIMIT 1"
                    ),
                    {"tid": tenant_id, "lid": str(log_id)},
                ).fetchone()
            if existing is not None:
                logger.info("p13_task: log_id=%s already_generated — skip", log_id)
                return {"status": "already_generated"}
        except Exception as exc:
            logger.warning("p13_task: idempotency gate failed: %s", type(exc).__name__)

    # 2. Cost-Cap-Vorcheck (generate_variants selbst ist capless!)
    if not _check_cost_cap(tenant_id):
        _send_cost_notice(tenant_id)
        return {"status": "skipped", "reason": "paused_for_cost"}

    # 3. Manuelle Idee anlegen (Spiegel von api/ideas.py:1294-1335)
    idea_id = _create_manual_idea(tenant_id, idea_text, log_id)
    if idea_id is None:
        return {"status": "error", "reason": "idea_creation_failed"}

    # 4. Varianten generieren (in-process, Muster api/ideas.py:504)
    variants = _run_generate_variants(idea_id)
    if not variants:
        # Marker entfernen + freundliche Notiz
        _clear_pending_marker(tenant_id, idea_id)
        _send_no_variants_notice(tenant_id)
        return {"status": "skipped", "reason": "no_valid_variants"}

    # 5. 3 Richtungen in den Chat
    return _send_variants_message(tenant_id, idea_id, variants)


# ---------------------------------------------------------------------------
# Interne Helfer
# ---------------------------------------------------------------------------


def _check_cost_cap(tenant_id: str) -> bool:
    """Gibt True zurück wenn Budget noch vorhanden (< Cap). Fail-open: True bei DB-Fehler."""
    try:
        from datetime import date

        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT cost_usd FROM daily_cost_tenant "
                    "WHERE tenant_id = :tid AND date = :date"
                ),
                {"tid": tenant_id, "date": date.today().isoformat()},
            ).fetchone()
            if row and float(row[0]) >= _COST_CAP_USD:
                logger.warning(
                    "p13_task: cost cap reached for tenant=%s (%.4f >= %.4f)",
                    tenant_id,
                    float(row[0]),
                    _COST_CAP_USD,
                )
                return False
        return True
    except Exception as exc:
        logger.warning("p13_task: cost_cap check failed (fail-open): %s", type(exc).__name__)
        return True  # fail-open: lieber generieren als blockieren


def _create_manual_idea(
    tenant_id: str,
    idea_text: str,
    log_id: str | None,
) -> str | None:
    """Legt eine manuelle Idee an (Spiegel von api/ideas.py:1294-1335).

    find-or-create Source type='manual' → Stub-SourceItem → content_ideas-INSERT.
    Gibt idea_id (str) oder None bei Fehler zurück.
    """
    try:
        with sync_session_factory() as db:
            # find-or-create Source type='manual' (E3: tenant-scoped)
            source_row = db.execute(
                text(
                    "SELECT id FROM sources "
                    "WHERE tenant_id = :tid AND type = 'manual' LIMIT 1"
                ),
                {"tid": tenant_id},
            ).fetchone()
            if source_row:
                source_id = str(source_row[0])
            else:
                source_id = str(uuid.uuid4())
                db.execute(
                    text(
                        "INSERT INTO sources (id, tenant_id, type, url, title, status) "
                        "VALUES (:id, :tid, 'manual', 'manual://chat', 'Chat-Ideen', 'active')"
                    ),
                    {"id": source_id, "tid": tenant_id},
                )

            # Stub-SourceItem (kein echtes Transkript — Muster api/ideas.py:1311-1320)
            item_id = str(uuid.uuid4())
            db.execute(
                text(
                    "INSERT INTO source_items "
                    "(id, source_id, tenant_id, title, status, content_type) "
                    "VALUES (:id, :src, :tid, :title, 'analyzed', 'text')"
                ),
                {
                    "id": item_id,
                    "src": source_id,
                    "tid": tenant_id,
                    "title": idea_text[:80],
                },
            )

            # content_ideas-INSERT mit State-Marker
            idea_id = str(uuid.uuid4())
            source_context: dict = {
                "source": "telegram_chat",
                "chat_variant_choice_pending": True,
            }
            if log_id is not None:
                source_context["source_log_id"] = str(log_id)

            db.execute(
                text(
                    "INSERT INTO content_ideas "
                    "(id, source_item_id, tenant_id, title, description, angle, "
                    " status, source_context) "
                    "VALUES (:id, :item, :tid, :title, :desc, 'manual', 'new', "
                    "        CAST(:ctx AS jsonb))"
                ),
                {
                    "id": idea_id,
                    "item": item_id,
                    "tid": tenant_id,
                    "title": idea_text[:80],
                    "desc": idea_text[:600],
                    "ctx": json.dumps(source_context),
                },
            )
            db.commit()
            return idea_id
    except Exception as exc:
        logger.warning("p13_task: create_manual_idea failed: %s", type(exc).__name__)
        return None


def _run_generate_variants(idea_id: str) -> list[dict]:
    """Ruft generate_variants in-process auf und lädt die Varianten (hook/story/these).

    Gibt leere Liste zurück bei Fehler oder keinen Varianten.
    Upsert in p12_variants_task ist idempotent → Race mit Pump unschädlich.
    """
    try:
        from tasks.p12_variants_task import generate_variants

        result = generate_variants.apply(args=[idea_id]).get(timeout=120)
        if not isinstance(result, dict) or result.get("status") not in ("ok", "already_exists"):
            logger.info(
                "p13_task: generate_variants not ok: %s",
                result.get("status") if isinstance(result, dict) else "unknown",
            )
            return []
    except Exception as exc:
        logger.warning("p13_task: generate_variants call failed: %s", type(exc).__name__)
        return []

    # Varianten laden (Reihenfolge hook→story→these wie api/ideas.py:1386-1387)
    return _load_variants(idea_id)


def _load_variants(idea_id: str) -> list[dict]:
    """Lädt Varianten in Reihenfolge hook(1) → story(2) → these(3).

    Tenant-scope nicht nötig hier (idea_id ist eindeutig + kein
    Cross-Tenant-Risiko bei internem Helfer).
    """
    try:
        with sync_session_factory() as db:
            rows = db.execute(
                text(
                    "SELECT id, variant_type, hook_text, body_outline "
                    "FROM idea_variants "
                    "WHERE idea_id = CAST(:iid AS uuid) "
                    "  AND variant_type IN ('hook', 'story', 'these') "
                    "ORDER BY CASE variant_type "
                    "  WHEN 'hook' THEN 1 "
                    "  WHEN 'story' THEN 2 "
                    "  WHEN 'these' THEN 3 "
                    "  ELSE 4 END"
                ),
                {"iid": idea_id},
            ).fetchall()
            return [
                {
                    "id": str(r[0]),
                    "variant_type": r[1],
                    "hook_text": r[2] or "",
                    "body_outline": r[3] or "",
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("p13_task: load_variants failed: %s", type(exc).__name__)
        return []


def _clear_pending_marker(tenant_id: str, idea_id: str) -> None:
    """Entfernt den chat_variant_choice_pending-Marker bei Fehlschlag."""
    try:
        with sync_session_factory() as db:
            db.execute(
                text(
                    "UPDATE content_ideas "
                    "SET source_context = source_context || CAST(:patch AS jsonb) "
                    "WHERE id = CAST(:id AS uuid) AND tenant_id = :tid"
                ),
                {
                    "patch": json.dumps({"chat_variant_choice_pending": False}),
                    "id": idea_id,
                    "tid": tenant_id,
                },
            )
            db.commit()
    except Exception as exc:
        logger.warning("p13_task: clear_pending_marker failed: %s", type(exc).__name__)


def _send_variants_message(tenant_id: str, idea_id: str, variants: list[dict]) -> dict:
    """Formatiert die 3 Aufhänger und sendet sie in den Chat (fail-open)."""
    # Emoji-Nummerierung wie im Plan (§2.2.5)
    emoji_map = {0: "1️⃣", 1: "2️⃣", 2: "3️⃣"}
    type_label = {"hook": "HOOK", "story": "STORY", "these": "THESE"}

    lines = ["Starke Idee! Drei Richtungen, wie wir das aufziehen können:"]
    for i, v in enumerate(variants[:3]):
        emoji = emoji_map.get(i, f"{i+1}.")
        label = type_label.get(v["variant_type"], v["variant_type"].upper())
        hook_text = (v.get("hook_text") or "").strip()[:200]
        lines.append(f"{emoji} {label}: {hook_text}")

    lines.append(
        "\nAntworte einfach mit 1, 2 oder 3 — "
        "dann stelle ich dir 2–3 kurze Rückfragen und schreibe deinen Post."
    )

    message = "\n".join(lines)
    if len(message) > _TELEGRAM_MAX_CHARS:
        message = message[:_TELEGRAM_MAX_CHARS]

    chat_id = _resolve_chat_id(tenant_id)
    if chat_id is None:
        logger.info("p13_task: no active chat link for tenant — variants not sent")
        return {
            "status": "ok",
            "sent": False,
            "reason": "no_chat_link",
            "idea_id": idea_id,
            "variants_count": len(variants),
        }

    try:
        from api.telegram import _send_telegram_message

        _send_telegram_message(chat_id, message)
        return {
            "status": "ok",
            "sent": True,
            "idea_id": idea_id,
            "variants_count": len(variants),
        }
    except Exception as exc:
        logger.warning("p13_task: telegram send failed: %s", type(exc).__name__)
        return {
            "status": "ok",
            "sent": False,
            "reason": "send_failed",
            "idea_id": idea_id,
            "variants_count": len(variants),
        }


def _try_p13_variant_choice(tenant_id: str, text: str) -> bool | dict:
    """Prüft ob ein Pending-Marker + gültiger Choice-Text vorliegt und verarbeitet ihn.

    Gate 2 in _route_inbound_message (Plan §3.1 Gate 2).
    Auch vom too_short-Bypass in _process_text aufgerufen.

    Returns:
        dict mit {"status": "ok", "routed_to": "p13_choice", ...} bei Treffer,
        False wenn kein Pending-Marker oder kein gültiger Choice-Token.
    """
    # Kurztext-Check: ≤40 Zeichen (strenge Wahl, kein Fließtext)
    text_stripped = (text or "").strip()
    if len(text_stripped) > 40:
        return False

    # Choice-Token parsen (1/2/3/eins/zwei/drei/hook/story/these)
    choice = _parse_choice_token(text_stripped)
    if choice is None:
        return False

    # Pending-Idee laden (tenant-scoped, max 24h, neueste zuerst)
    pending_idea = _load_pending_idea(tenant_id)
    if pending_idea is None:
        return False

    # Gewählte Variante laden
    variant = _get_variant_by_choice(pending_idea["idea_id"], choice)
    if variant is None:
        return False

    # Wahl persistieren (Spiegel von api/ideas.py:1460-1488)
    ok = _persist_choice(tenant_id, pending_idea["idea_id"], variant)
    if not ok:
        return False

    # p08_opener(mode='targeted', topic_idea_id=idea_id) starten
    opener_result = _start_targeted_session(tenant_id, pending_idea["idea_id"])
    if opener_result is None:
        return False

    return {
        "status": "ok",
        "routed_to": "p13_choice",
        "idea_id": pending_idea["idea_id"],
        "variant_type": variant["variant_type"],
        "session_id": opener_result.get("session_id"),
    }


def _parse_choice_token(text: str) -> int | None:
    """Parst 1/2/3/eins/zwei/drei/hook/story/these → 1/2/3 (1-basiert) oder None."""
    import re
    t = text.lower().strip()
    # Numerisch
    if re.match(r"^1$", t):
        return 1
    if re.match(r"^2$", t):
        return 2
    if re.match(r"^3$", t):
        return 3
    # Wortform
    if re.match(r"^eins?$", t):
        return 1
    if re.match(r"^zwei$", t):
        return 2
    if re.match(r"^drei$", t):
        return 3
    # Variant-Name
    if re.match(r"^hook$", t):
        return 1
    if re.match(r"^story$", t):
        return 2
    if re.match(r"^these$", t):
        return 3
    return None


def _load_pending_idea(tenant_id: str) -> dict | None:
    """Lädt die jüngste Pending-Idee des Tenants (Marker=true, ≤24h, E3-scoped)."""
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT id FROM content_ideas "
                    "WHERE tenant_id = :tid "
                    "  AND (source_context->>'chat_variant_choice_pending')::boolean = true "
                    "  AND created_at > now() - make_interval(hours => :window) "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"tid": tenant_id, "window": _P13_CHOICE_WINDOW_HOURS},
            ).fetchone()
            if row is None:
                return None
            return {"idea_id": str(row[0])}
    except Exception as exc:
        logger.warning("p13_task: load_pending_idea failed: %s", type(exc).__name__)
        return None


def _get_variant_by_choice(idea_id: str, choice: int) -> dict | None:
    """Lädt die Variante (1=hook, 2=story, 3=these) für eine Idee."""
    type_map = {1: "hook", 2: "story", 3: "these"}
    variant_type = type_map.get(choice)
    if variant_type is None:
        return None
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT id, variant_type, hook_text, body_outline "
                    "FROM idea_variants "
                    "WHERE idea_id = CAST(:iid AS uuid) AND variant_type = :vtype LIMIT 1"
                ),
                {"iid": idea_id, "vtype": variant_type},
            ).fetchone()
            if row is None:
                return None
            return {
                "id": str(row[0]),
                "variant_type": row[1],
                "hook_text": row[2] or "",
                "body_outline": row[3] or "",
            }
    except Exception as exc:
        logger.warning("p13_task: get_variant_by_choice failed: %s", type(exc).__name__)
        return None


def _persist_choice(tenant_id: str, idea_id: str, variant: dict) -> bool:
    """Persistiert die gewählte Variante (Spiegel von api/ideas.py:1460-1488).

    - is_chosen Reset + Set in idea_variants
    - hook_suggestion := variant.hook_text in content_ideas
    - source_context ||= {chosen_variant_id, body_outline, chat_variant_choice_pending: false}
    """
    try:
        with sync_session_factory() as db:
            # is_chosen Reset (alle Varianten dieser Idee)
            db.execute(
                text(
                    "UPDATE idea_variants SET is_chosen = false "
                    "WHERE idea_id = CAST(:iid AS uuid)"
                ),
                {"iid": idea_id},
            )
            # is_chosen Set für die gewählte Variante
            db.execute(
                text(
                    "UPDATE idea_variants SET is_chosen = true "
                    "WHERE id = CAST(:vid AS uuid)"
                ),
                {"vid": variant["id"]},
            )
            # Hook + Outline in content_ideas spiegeln + Marker löschen
            patch = json.dumps(
                {
                    "chosen_variant_id": variant["id"],
                    "body_outline": variant["body_outline"],
                    "chat_variant_choice_pending": False,
                }
            )
            db.execute(
                text(
                    "UPDATE content_ideas "
                    "SET hook_suggestion = :hook, "
                    "    source_context = source_context || CAST(:patch AS jsonb) "
                    "WHERE id = CAST(:id AS uuid) AND tenant_id = :tid"
                ),
                {
                    "hook": variant["hook_text"][:500] if variant["hook_text"] else None,
                    "patch": patch,
                    "id": idea_id,
                    "tid": tenant_id,
                },
            )
            db.commit()
        return True
    except Exception as exc:
        logger.warning("p13_task: persist_choice failed: %s", type(exc).__name__)
        return False


def _start_targeted_session(tenant_id: str, idea_id: str) -> dict | None:
    """Startet p08_opener(mode='targeted', topic_idea_id=idea_id) + sendet die Frage.

    Muster: random_smart_scheduler.py:84-109 (_send_opening_question).
    Gibt dict mit session_id + question_text oder None bei Fehler.
    """
    try:
        from services.p08_service import p08_opener

        opener = p08_opener(tenant_id, mode="targeted", topic_idea_id=idea_id)
        # Opener-Frage in den Chat senden (Muster random_smart_scheduler.py:104)
        chat_id = _resolve_chat_id(tenant_id)
        if chat_id is not None:
            try:
                from api.telegram import _send_telegram_message

                _send_telegram_message(chat_id, opener.question_text)
            except Exception as exc:
                logger.warning(
                    "p13_task: opener send failed (session created): %s",
                    type(exc).__name__,
                )
        return {"session_id": opener.session_id, "question_text": opener.question_text}
    except Exception as exc:
        logger.warning("p13_task: start_targeted_session failed: %s", type(exc).__name__)
        return None


def _resolve_chat_id(tenant_id: str) -> int | None:
    """Lookup active Telegram chat_id (wiederverwendet Muster telegram_task.py:107-128)."""
    try:
        from tasks.telegram_task import _resolve_chat_id as _resolve

        return _resolve(tenant_id)
    except Exception as exc:
        logger.warning("p13_task: chat_id resolve failed: %s", type(exc).__name__)
        return None


def _send_cost_notice(tenant_id: str) -> None:
    """Sendet freundliche Kosten-Notiz (Muster post_feedback_task.py:368-381)."""
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
        logger.warning("p13_task: cost notice send failed: %s", type(exc).__name__)


def _send_no_variants_notice(tenant_id: str) -> None:
    """Sendet freundliche Notiz wenn Varianten-Generierung fehlschlug."""
    try:
        chat_id = _resolve_chat_id(tenant_id)
        if chat_id is None:
            return
        from api.telegram import _send_telegram_message

        _send_telegram_message(
            chat_id,
            "Hmm, die Varianten konnte ich gerade nicht generieren — versuch es gleich nochmal!",
        )
    except Exception as exc:
        logger.warning("p13_task: no-variants notice send failed: %s", type(exc).__name__)
