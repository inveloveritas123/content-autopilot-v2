"""
Voice-Drift-Detector (Issue #76).

Workflow:
1. Beat-Job check_drift_triggers: prüft alle Tenants auf 10er-Post-Schwelle
2. run_voice_drift: lädt aktives Voice-Profil + letzte 10 Posts, ruft Anthropic,
   schreibt voice_drift_observation, sendet WS-Push
"""

import asyncio
import json
import logging
import uuid
import uuid as uuid_module

import httpx
from sqlalchemy import text

from models.base import sync_session_factory
from services.prompt_loader import get_default_prompt_loader
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Geschätzte Token-Kosten für Cost-Cap-Check (~4000 input, 512 output)
_ESTIMATED_INPUT_TOKENS = 4000
_ESTIMATED_OUTPUT_TOKENS = 512


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _safe_uuid_list(ids: list) -> list:
    """Validiert alle Elemente als UUIDs — wirft ValueError bei ungültigem Format."""
    result = []
    for item in ids:
        try:
            result.append(str(uuid_module.UUID(str(item))))
        except ValueError:
            raise ValueError(f"Ungültige UUID in trigger_post_ids: {item!r}")
    return result


def _extract_json_from_text(raw: str) -> dict:
    """JSON aus LLM-Output parsen — entfernt Markdown-Code-Zaun falls vorhanden."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        inner_lines = lines[1:]
        if inner_lines and inner_lines[-1].strip() == "```":
            inner_lines = inner_lines[:-1]
        cleaned = "\n".join(inner_lines).strip()
    return json.loads(cleaned)


async def _run_cost_check(tenant_id: str, estimated_cost: float) -> None:
    """Async Cost-Cap-Check — via asyncio.run() aus Celery aufgerufen."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as async_sm

    from config import settings
    from services.cost_cap import CostCapMiddleware

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    AsyncSessionLocal = async_sm(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with AsyncSessionLocal() as session:
            mw = CostCapMiddleware(session)
            await mw.check_and_record(tenant_id, estimated_cost)
    finally:
        await engine.dispose()


def _has_pending_observation(session, tenant_id: str) -> bool:
    """Prüft ob bereits ein pending_review Drift-Run für diesen Tenant existiert (letzte 24h)."""
    row = session.execute(
        text(
            "SELECT 1 FROM voice_drift_observation "
            "WHERE tenant_id = :t "
            "AND status = 'pending_review' "
            "AND created_at > now() - interval '1 day' "
            "LIMIT 1"
        ),
        {"t": tenant_id},
    ).fetchone()
    return row is not None


def _get_all_tenant_ids(session) -> list:
    """Alle Tenant-IDs mit aktivem Voice-Profil laden."""
    rows = session.execute(
        text("SELECT DISTINCT tenant_id FROM tenant_voice_profile WHERE is_active = true")
    ).fetchall()
    return [str(row[0]) for row in rows]


def _count_todays_approved_posts(session, tenant_id: str) -> int:
    """Anzahl heute freigegebener Posts für einen Tenant."""
    row = session.execute(
        text(
            "SELECT COUNT(*) FROM content_pieces "
            "WHERE tenant_id = :t "
            "AND status IN ('approved', 'published') "
            "AND created_at >= CURRENT_DATE"
        ),
        {"t": tenant_id},
    ).scalar()
    return int(row or 0)


# ---------------------------------------------------------------------------
# Beat-Job: Trigger-Check
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.voice_drift_task.check_drift_triggers")
def check_drift_triggers():
    """Beat-Job: prüft alle Tenants auf Drift-Trigger (10er-Post-Schwelle)."""
    triggered = 0
    skipped = 0

    with sync_session_factory() as session:
        tenant_ids = _get_all_tenant_ids(session)
        logger.info("check_drift_triggers: prüfe %d Tenants", len(tenant_ids))

        for tenant_id in tenant_ids:
            count = _count_todays_approved_posts(session, tenant_id)
            if count > 0 and count % 10 == 0:
                # Doppel-Trigger verhindern
                if _has_pending_observation(session, tenant_id):
                    logger.info(
                        "check_drift_triggers: tenant=%s count=%d — bereits pending, übersprungen",
                        tenant_id,
                        count,
                    )
                    skipped += 1
                    continue
                run_voice_drift.delay(tenant_id, trigger_type="post_threshold")
                logger.info(
                    "check_drift_triggers: tenant=%s count=%d — Drift-Task angestoßen",
                    tenant_id,
                    count,
                )
                triggered += 1

    logger.info("check_drift_triggers: triggered=%d skipped=%d", triggered, skipped)
    return {"triggered": triggered, "skipped": skipped}


# ---------------------------------------------------------------------------
# Haupt-Task: Voice-Drift-Analyse
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.voice_drift_task.run_voice_drift", bind=True)
def run_voice_drift(
    self,
    tenant_id: str,
    trigger_type: str = "post_threshold",
    trigger_post_ids: list | None = None,
    voice_feedback_ids: list | None = None,
) -> dict:
    """Voice-Drift-Analyse für einen Tenant.

    Args:
        tenant_id:          Tenant-Identifier (UUID-String)
        trigger_type:       Auslöser (post_threshold | manual | feedback)
        trigger_post_ids:   Optionale Liste von Post-IDs, die den Trigger ausgelöst haben
        voice_feedback_ids: Optionale Liste von Voice-Feedback-IDs

    Returns:
        {"status": "done"|"skipped"|"paused_for_cost"|"failed", ...}
    """
    from services.kill_switch import KillSwitchTriggered, check_kill_switch

    try:
        check_kill_switch(tenant_id)
    except KillSwitchTriggered:
        return {"status": "aborted", "reason": "tenant_disabled"}
    logger.info("run_voice_drift: tenant=%s trigger_type=%s", tenant_id, trigger_type)

    # ------------------------------------------------------------------
    # 1. Doppel-Trigger-Guard
    # ------------------------------------------------------------------
    with sync_session_factory() as session:
        if _has_pending_observation(session, tenant_id):
            logger.info("run_voice_drift: tenant=%s — bereits pending, übersprungen", tenant_id)
            return {"status": "skipped", "reason": "already_pending"}

    try:
        # ------------------------------------------------------------------
        # 2. Cost-Cap prüfen
        # ------------------------------------------------------------------
        from services.cost_cap import CostCapExceeded
        from services.pipeline_llm import estimate_tier_cost

        estimated_cost = estimate_tier_cost("S6", _ESTIMATED_INPUT_TOKENS, _ESTIMATED_OUTPUT_TOKENS)
        try:
            asyncio.run(_run_cost_check(tenant_id, estimated_cost))
        except CostCapExceeded:
            logger.warning(
                "run_voice_drift: tenant=%s — daily cost cap exceeded, pausiert", tenant_id
            )
            return {"status": "paused_for_cost"}

        # ------------------------------------------------------------------
        # 3. Aktives Voice-Profil laden
        # ------------------------------------------------------------------
        # Deterministische Aktiv-Row-Auflösung über den Fassaden-Resolver
        # (behebt Nichtdeterminismus bei mehreren aktiven Rows / Projekt-Rows;
        # vorher: WHERE is_active=true LIMIT 1 ohne ORDER BY/Projektfilter).
        from services.canonical_profiles import pick_active

        with sync_session_factory() as session:
            rows = session.execute(
                text(
                    "SELECT project_id, version, payload FROM tenant_voice_profile "
                    "WHERE tenant_id = :t AND is_active = true"
                ),
                {"t": tenant_id},
            ).fetchall()

        candidates = [
            {
                "project_id": r[0],
                "version": r[1],
                "payload": r[2] if isinstance(r[2], dict) else json.loads(r[2]),
            }
            for r in rows
        ]
        chosen = pick_active(candidates)
        if not chosen:
            logger.warning(
                "run_voice_drift: tenant=%s — kein aktives Voice-Profil gefunden", tenant_id
            )
            return {"status": "failed", "error": "no_active_voice_profile"}

        voice_version = chosen["version"]
        voice_payload = chosen["payload"]

        # ------------------------------------------------------------------
        # 4. Letzte 10 freigegebene Posts laden
        # ------------------------------------------------------------------
        with sync_session_factory() as session:
            post_rows = session.execute(
                text(
                    "SELECT id, content_text FROM content_pieces "
                    "WHERE tenant_id = :t "
                    "AND status IN ('approved', 'published') "
                    "ORDER BY created_at DESC LIMIT 10"
                ),
                {"t": tenant_id},
            ).fetchall()

        recent_posts = [{"id": str(row[0]), "content": (row[1] or "")[:2000]} for row in post_rows]
        post_ids_for_trigger = trigger_post_ids or [str(row[0]) for row in post_rows]

        # ------------------------------------------------------------------
        # 5. Voice-Feedback laden (graceful, Tabelle ggf. noch nicht existierend)
        # ------------------------------------------------------------------
        feedback_rows = []
        try:
            with sync_session_factory() as session:
                feedback_rows = session.execute(
                    text(
                        "SELECT id, feedback_text, field_path FROM voice_feedback "
                        "WHERE tenant_id = :t AND processed_at IS NULL "
                        "ORDER BY created_at LIMIT 20"
                    ),
                    {"t": tenant_id},
                ).fetchall()
        except Exception as fb_err:
            logger.debug("run_voice_drift: voice_feedback nicht verfügbar (Issue #77): %s", fb_err)
            feedback_rows = []

        user_feedback = [{"text": row[1] or "", "field": row[2] or ""} for row in feedback_rows]

        # ------------------------------------------------------------------
        # 6. Prompt laden
        # ------------------------------------------------------------------
        loader = get_default_prompt_loader()
        loaded = loader.load("VOICE_DRIFT")
        logger.debug("run_voice_drift: prompt sha=%s geladen", loaded.sha[:12])
        if "{context_json}" not in loaded.user_prompt_template:
            raise ValueError(
                "VOICE_DRIFT User-Prompt-Template hat keinen {context_json}-Placeholder"
            )

        # ------------------------------------------------------------------
        # 7. User-Prompt bauen
        # ------------------------------------------------------------------
        context_payload = {
            "active_voice_profile": voice_payload,
            "recent_posts": recent_posts,
            "user_feedback": user_feedback,
        }
        context_json = json.dumps(context_payload, ensure_ascii=False)

        user_prompt = loaded.user_prompt_template.replace("{context_json}", context_json)

        # ------------------------------------------------------------------
        # 8. LLM-Call über EU-Seam (Issue #111 — kein direktes Anthropic-SDK)
        # ------------------------------------------------------------------
        from services.pipeline_llm import call_pipeline_llm

        llm_result = call_pipeline_llm(
            prompt_key="VOICE_DRIFT",
            system_prompt=loaded.system_prompt,
            user_content=user_prompt,
            tenant_id=tenant_id,
            max_tokens=1024,
        )
        raw_text = llm_result.text
        input_tokens = llm_result.input_tokens or _ESTIMATED_INPUT_TOKENS
        output_tokens = llm_result.output_tokens or _ESTIMATED_OUTPUT_TOKENS
        logger.info(
            "run_voice_drift: tenant=%s input=%d output=%d (via EU-Seam tier=%s)",
            tenant_id,
            input_tokens,
            output_tokens,
            llm_result.tier,
        )

        # ------------------------------------------------------------------
        # 9. Output parsen — erwartete Struktur:
        #    {"proposals": [...], "summary": "...", "confidence": 0.0-1.0}
        # ------------------------------------------------------------------
        try:
            output_json = _extract_json_from_text(raw_text)
        except json.JSONDecodeError as parse_err:
            logger.warning(
                "run_voice_drift: tenant=%s — JSON-Parsing fehlgeschlagen: %s",
                tenant_id,
                parse_err,
            )
            output_json = {"proposals": [], "summary": raw_text[:500], "confidence": 0.0}

        proposals = output_json.get("proposals", [])
        summary = output_json.get("summary", "")
        confidence = output_json.get("confidence", 0.0)

        # ------------------------------------------------------------------
        # 10. DB-Insert in voice_drift_observation
        #     Spalten lt. Migration 018: id, tenant_id, trigger_post_ids,
        #     current_voice_version, suggested_changes, status, created_at
        # ------------------------------------------------------------------
        obs_id = str(uuid.uuid4())
        with sync_session_factory() as session:
            session.execute(
                text(
                    "INSERT INTO voice_drift_observation "
                    "(id, tenant_id, trigger_post_ids, current_voice_version, "
                    "suggested_changes, status, created_at) "
                    "VALUES (:id, :t, CAST(:post_ids AS uuid[]), :voice_version, "
                    "CAST(:suggested_changes AS jsonb), 'pending_review', now())"
                ),
                {
                    "id": obs_id,
                    "t": tenant_id,
                    "post_ids": "{" + ",".join(_safe_uuid_list(post_ids_for_trigger)) + "}",
                    "voice_version": voice_version,
                    "suggested_changes": json.dumps(
                        {
                            "proposals": proposals,
                            "summary": summary,
                            "confidence": confidence,
                        },
                        ensure_ascii=False,
                    ),
                },
            )
            session.commit()

        logger.info(
            "run_voice_drift: tenant=%s obs_id=%s proposals=%d confidence=%.2f",
            tenant_id,
            obs_id,
            len(proposals),
            confidence,
        )

        # ------------------------------------------------------------------
        # 11. WebSocket-Notification
        # ------------------------------------------------------------------
        try:
            resp = httpx.post(
                "http://localhost:8000/internal/notify",
                json={
                    "channel": f"tenant:{tenant_id}:setup",
                    "message": {
                        "type": "drift_available",
                        "observation_id": obs_id,
                        "summary": summary,
                    },
                },
                timeout=5,
            )
            clients_reached = resp.json().get("sent", 0) if resp.is_success else 0
            logger.info(
                "run_voice_drift: WS push tenant=%s clients_reached=%d",
                tenant_id,
                clients_reached,
            )
        except Exception as ws_err:
            logger.warning("run_voice_drift: WS push fehlgeschlagen: %s", ws_err)

        # ------------------------------------------------------------------
        # 12. Return
        # ------------------------------------------------------------------
        return {
            "status": "done",
            "observation_id": obs_id,
            "proposals_count": len(proposals),
        }

    except Exception as exc:
        logger.exception("run_voice_drift: tenant=%s FAILED — %s", tenant_id, exc)
        return {"status": "failed", "error": str(exc)}
