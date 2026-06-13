"""P17 je-Transkript-Beobachter (Issue #41, Figma Bahn 5).

Beobachtet **jedes** fertige Transkript und schlägt inkrementelle Updates an
Voice / Werte / Avatar vor — geschrieben als ``voice_drift_observation``-Rows mit
``entity_type``, die der Mensch über den bereits gebauten Drift-Decide-Pfad
(``api/brand_voice.py:decide_drift_observation``, #43 Schritt 4) bestätigt.

Additiv zum Batch-Pfad ``tasks/voice_drift_task.py`` (10er-Post-Schwelle, nur Voice);
der bleibt unangetastet.

Reine Logik (Gates, Normalisierung, Emit-Auswahl) liegt dep-frei in
``services/p17_observer_core.py`` (lokal Py 3.9-testbar). Diese Datei ist das Wiring.

Grenzen (ehrlich):
* **Prompt = Chris (#22):** Solange der P17-System-Prompt leer ist (Eigenkonstruktions-
  Headings), fail-opent der Beobachter (``skipped/prompt_unavailable``). Maschinerie
  gebaut & mock-belegt; realer Lauf wartet auf Chris' Prompt-Headings.
* **Idempotenz migrationsfrei** über ``suggested_changes->>'source_item_id'``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

import httpx
from sqlalchemy import text

from models.base import sync_session_factory
from services.prompt_loader import get_default_prompt_loader
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

ANTHROPIC_PRICING_KEY = "claude-sonnet-4-6"  # Pricing-Key für cost_cap (ohne Datum-Suffix)
_ESTIMATED_INPUT_TOKENS = 4000
_ESTIMATED_OUTPUT_TOKENS = 512

#: entity_type → canonical_profiles-profile_type (für die Versions-Auflösung).
_ENTITY_TO_PROFILE_TYPE = {
    "voice": "voice_profile",
    "values": "customer_values",
    "avatar": "audience_avatar",
}


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


def _already_observed(session, tenant_id: str, source_item_id: str) -> bool:
    """True, wenn für (tenant, source_item) bereits eine Observation existiert (Idempotenz)."""
    row = session.execute(
        text(
            "SELECT 1 FROM voice_drift_observation "
            "WHERE tenant_id = :t "
            "AND suggested_changes->>'source_item_id' = :sid "
            "LIMIT 1"
        ),
        {"t": tenant_id, "sid": str(source_item_id)},
    ).fetchone()
    return row is not None


def _load_transcript(session, tenant_id: str, source_item_id: str) -> str:
    """Lädt den Transkript-Text (E3-tenant-gescopet)."""
    row = session.execute(
        text("SELECT transcript_text FROM source_items WHERE id = :sid AND tenant_id = :t"),
        {"sid": str(source_item_id), "t": tenant_id},
    ).fetchone()
    return (row[0] or "") if row else ""


def _active_version(session, entity_type: str, tenant_id: str) -> int:
    """Aktive Version einer Entität (informativ für current_voice_version); 0 wenn keine."""
    from services.canonical_profiles import TABLE_MAP

    profile_type = _ENTITY_TO_PROFILE_TYPE[entity_type]
    table = TABLE_MAP[profile_type]  # SQL-sicher: nur Whitelist-Werte
    row = session.execute(
        text(
            f"SELECT version FROM {table} "
            "WHERE tenant_id = :t AND is_active = true "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"t": tenant_id},
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _notify_drift_available(tenant_id: str, obs_id: str, summary: str) -> None:
    """Best-effort WebSocket-Push (wie voice_drift_task)."""
    try:
        httpx.post(
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
    except Exception as ws_err:
        logger.warning("observe_transcript: WS push fehlgeschlagen: %s", ws_err)


@celery_app.task(name="tasks.p17_transcript_observer_task.observe_transcript", bind=True)
def observe_transcript(
    self,
    tenant_id: str,
    source_item_id: str,
    trigger_type: str = "transcript",
) -> dict:
    """Beobachtet ein Transkript und legt Voice/Werte/Avatar-Drift-Vorschläge an.

    Returns:
        {"status": "done"|"skipped"|"paused_for_cost"|"aborted"|"failed", ...}
    """
    from services import p17_observer_core as core
    from services.kill_switch import KillSwitchTriggered, check_kill_switch

    try:
        check_kill_switch(tenant_id)
    except KillSwitchTriggered:
        return {"status": "aborted", "reason": "tenant_disabled"}

    logger.info(
        "observe_transcript: tenant=%s source_item=%s trigger=%s",
        tenant_id,
        source_item_id,
        trigger_type,
    )

    try:
        # 1. Idempotenz-Guard
        with sync_session_factory() as session:
            if _already_observed(session, tenant_id, source_item_id):
                logger.info(
                    "observe_transcript: tenant=%s source_item=%s — bereits beobachtet",
                    tenant_id,
                    source_item_id,
                )
                return {"status": "skipped", "reason": "already_observed"}

            # 2. Transkript laden (E3-gescopet)
            transcript = _load_transcript(session, tenant_id, source_item_id)

        if not core.transcript_is_observable(transcript):
            return {"status": "skipped", "reason": "no_transcript"}

        # 3. Cost-Cap
        from services.cost_cap import CostCapExceeded, estimate_anthropic_cost

        estimated_cost = estimate_anthropic_cost(
            ANTHROPIC_PRICING_KEY, _ESTIMATED_INPUT_TOKENS, _ESTIMATED_OUTPUT_TOKENS
        )
        try:
            asyncio.run(_run_cost_check(tenant_id, estimated_cost))
        except CostCapExceeded:
            logger.warning("observe_transcript: tenant=%s — cost cap, pausiert", tenant_id)
            return {"status": "paused_for_cost"}

        # 4. Aktive Profile laden → entity-keyed
        from services.canonical_profiles import load_active_profiles

        loaded_profiles = load_active_profiles(tenant_id)
        profiles_by_entity = {
            ent: (loaded_profiles.get(ptype, {}) or {}).get("payload") or {}
            for ptype, ent in core.PROFILE_TYPE_TO_ENTITY.items()
        }

        # 5. Prompt laden + Gate (#22 / Chris)
        loader = get_default_prompt_loader()
        loaded = loader.load("P17")
        if not core.prompt_is_usable(loaded.system_prompt):
            logger.warning(
                "observe_transcript: tenant=%s — P17-System-Prompt leer (#22, Chris), "
                "fail-open skip",
                tenant_id,
            )
            return {"status": "skipped", "reason": "prompt_unavailable"}

        # 6. User-Prompt bauen (Template-Placeholder oder Anhang)
        context_json = json.dumps(
            core.build_user_context(transcript, profiles_by_entity), ensure_ascii=False
        )
        template = loaded.user_prompt_template or ""
        if "{context_json}" in template:
            user_prompt = template.replace("{context_json}", context_json)
        else:
            user_prompt = (template + "\n\n" + context_json).strip()

        # 7. LLM-Call über EU-Router-Seam (kein direkter Provider-Call)
        from services.pipeline_llm import call_pipeline_llm

        llm_result = call_pipeline_llm(
            prompt_key="P17",
            system_prompt=loaded.system_prompt,
            user_content=user_prompt,
            tenant_id=tenant_id,
        )

        # 8. Parsen + Normalisieren
        try:
            parsed = core.extract_json(llm_result.text)
        except ValueError as parse_err:
            logger.warning(
                "observe_transcript: tenant=%s — JSON-Parsing fehlgeschlagen: %s",
                tenant_id,
                parse_err,
            )
            return {"status": "skipped", "reason": "unparseable_output"}

        normalized = core.normalize_p17_output(parsed)
        to_emit = core.observations_to_emit(normalized, str(source_item_id))

        if not to_emit:
            logger.info("observe_transcript: tenant=%s — keine Vorschläge", tenant_id)
            return {"status": "done", "observations": [], "proposals_count": 0}

        # 9. Pro Entität eine Observation-Row anlegen
        emitted: list[dict] = []
        with sync_session_factory() as session:
            for item in to_emit:
                entity_type = item["entity_type"]
                obs_id = str(uuid.uuid4())
                version = _active_version(session, entity_type, tenant_id)
                session.execute(
                    text(
                        "INSERT INTO voice_drift_observation "
                        "(id, tenant_id, trigger_post_ids, current_voice_version, "
                        "suggested_changes, status, entity_type, created_at) "
                        "VALUES (:id, :t, CAST(:post_ids AS uuid[]), :version, "
                        "CAST(:suggested_changes AS jsonb), 'pending_review', :entity_type, now())"
                    ),
                    {
                        "id": obs_id,
                        "t": tenant_id,
                        "post_ids": "{}",  # Transkript-getrieben → keine Post-IDs
                        "version": version,
                        "suggested_changes": json.dumps(
                            item["suggested_changes"], ensure_ascii=False
                        ),
                        "entity_type": entity_type,
                    },
                )
                emitted.append(
                    {
                        "observation_id": obs_id,
                        "entity_type": entity_type,
                        "summary": item["suggested_changes"].get("summary", ""),
                    }
                )
            session.commit()

        # 10. WS-Notify (best-effort, je Observation)
        for e in emitted:
            _notify_drift_available(tenant_id, e["observation_id"], e["summary"])

        logger.info(
            "observe_transcript: tenant=%s source_item=%s observations=%d",
            tenant_id,
            source_item_id,
            len(emitted),
        )
        return {
            "status": "done",
            "observations": emitted,
            "proposals_count": sum(
                len(i["suggested_changes"].get("proposals", [])) for i in to_emit
            ),
        }

    except Exception as exc:
        logger.exception(
            "observe_transcript: tenant=%s source_item=%s FAILED — %s",
            tenant_id,
            source_item_id,
            exc,
        )
        return {"status": "failed", "error": str(exc)}
