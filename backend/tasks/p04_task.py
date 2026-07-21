"""
P04-Service — Audience-Avatar-Vertiefung aus P01-Kundenkontext.

Workflow:
1. Setup-Pipeline-Run in DB anlegen (status='running')
2. Tageskosten-Cap prüfen (CostCapMiddleware, async via asyncio.run)
3. Prompt laden (PromptLoader, sync via Nextcloud/localfs)
4. LLM-Call über call_pipeline_llm (Seam → Router, kein direkter SDK-Aufruf)
5. JSON-Parsing + Schema-Validierung (jsonschema)
   [HYPOTHESE]-Markierungen werden NICHT gefiltert — durchgereicht wie empfangen.
6. Insert in tenant_audience_avatar (is_active=False)
7. Audit-Update in setup_pipeline_run (status='done')

Umgestellt: 2026-06-11 (P5-anthropic-provider.md)
  - anthropic-SDK-Bypass entfernt (ANTHROPIC_MODEL_ID entfernt)
  - Modell-ID kommt jetzt aus PipelineLLMResult.model_id
  - Kosten-Schätzung über estimate_tier_cost statt estimate_anthropic_cost
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid

from sqlalchemy import text

from models.base import sync_session_factory
from services.pipeline_llm import (
    call_pipeline_llm,
    estimate_tier_cost,
    resolve_tier,
)
from services.prompt_loader import get_default_prompt_loader
from services.schema_transformer import build_canonical_meta, finalize_canonical
from tasks.canonical_wiring import fetch_tenant_meta, now_iso
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _extract_json_from_text(raw: str) -> dict:
    """JSON aus dem LLM-Output parsen — entfernt Markdown-Code-Zaun falls vorhanden."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        inner_lines = lines[1:]
        if inner_lines and inner_lines[-1].strip() == "```":
            inner_lines = inner_lines[:-1]
        cleaned = "\n".join(inner_lines).strip()
    return json.loads(cleaned)


async def _run_cost_check(tenant_id: str, estimated_cost: float) -> None:
    """Async Cost-Cap-Check — soll via asyncio.run() aus Celery aufgerufen werden."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as async_sm

    from config import settings
    from services.cost_cap import CostCapMiddleware
    from services.rls import tenant_session

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    AsyncSessionLocal = async_sm(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with tenant_session(AsyncSessionLocal, tenant_id) as session:
            mw = CostCapMiddleware(session)
            await mw.check_and_record(tenant_id, estimated_cost)
    finally:
        await engine.dispose()


async def _record_actual_cost(tenant_id: str, actual_cost: float) -> None:
    """Actual-Cost nach erfolgreichem LLM-Call ins daily_cost_tenant schreiben."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as async_sm

    from config import settings
    from services.cost_cap import CostCapMiddleware
    from services.rls import tenant_session

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    AsyncSessionLocal = async_sm(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with tenant_session(AsyncSessionLocal, tenant_id) as session:
            mw = CostCapMiddleware(session)
            # estimated_cost=0 → nur record, kein double-check
            await mw.check_and_record(tenant_id, 0.0, actual_cost_usd=actual_cost)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Celery Task
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.p04_task.run_p04", bind=True, max_retries=2)
def run_p04(
    self,
    tenant_id: str,
    p01_payload: dict,
    transcript: str | None = None,
    project_id: str | None = None,
) -> dict:
    """P04-Avatar-Vertiefung: Psychologisches Audience-Avatar aus P01-Kontext.

    Args:
        tenant_id:   ID des Tenants (z.B. UUID-String)
        p01_payload: Pflicht — Output-Dict aus P01 (Kundenkontext)
        transcript:  Optional — Transkript-Text für zusätzlichen Kontext

    Returns:
        {"run_id": str, "status": "done"|"paused_for_cost"|"failed", "error": str|None}
    """
    from services.kill_switch import KillSwitchTriggered, check_kill_switch

    try:
        check_kill_switch(tenant_id)
    except KillSwitchTriggered:
        return {"status": "aborted", "reason": "tenant_disabled"}
    run_id = str(uuid.uuid4())
    start_ts = time.monotonic()

    # ------------------------------------------------------------------
    # Dependency-Check: P01-Payload muss vorhanden sein
    # ------------------------------------------------------------------
    if not p01_payload or not isinstance(p01_payload, dict):
        logger.error("p04 run_id=%s tenant=%s: p01_payload fehlt oder ungültig", run_id, tenant_id)
        return {"run_id": run_id, "status": "failed", "error": "p01_payload_missing"}

    # ------------------------------------------------------------------
    # 1. Setup-Pipeline-Run anlegen
    # ------------------------------------------------------------------
    with sync_session_factory() as session:
        session.execute(
            text(
                "INSERT INTO setup_pipeline_run (id, tenant_id, stage, status, created_at) "
                "VALUES (:id, :tenant_id, 'p04', 'running', now())"
            ),
            {"id": run_id, "tenant_id": tenant_id},
        )
        session.commit()
    logger.info("p04 run_id=%s tenant=%s: pipeline run created", run_id, tenant_id)

    try:
        # ------------------------------------------------------------------
        # 2. Cost-Cap prüfen
        # ------------------------------------------------------------------
        from services.cost_cap import CostCapExceeded
        from services.llm import BudgetExceededError

        _tier, _ = resolve_tier("P04")
        estimated_cost = estimate_tier_cost(_tier, 3000, 1500)
        try:
            asyncio.run(_run_cost_check(tenant_id, estimated_cost))
        except (CostCapExceeded, BudgetExceededError):
            logger.warning(
                "p04 run_id=%s tenant=%s: daily cost cap exceeded, pausing",
                run_id,
                tenant_id,
            )
            with sync_session_factory() as session:
                session.execute(
                    text("UPDATE setup_pipeline_run SET status='paused_for_cost' " "WHERE id=:id"),
                    {"id": run_id},
                )
                session.commit()
            return {"run_id": run_id, "status": "paused_for_cost"}

        # ------------------------------------------------------------------
        # 3. Prompt laden (sync via Nextcloud/localfs)
        # ------------------------------------------------------------------
        loader = get_default_prompt_loader()
        loaded = loader.load("P04")
        prompt_version_hash = loaded.sha
        logger.debug("p04 run_id=%s: prompt sha=%s geladen", run_id, prompt_version_hash[:12])

        # ------------------------------------------------------------------
        # 4. LLM-Call über den Seam (kein direkter SDK-Aufruf)
        # ------------------------------------------------------------------
        # User-Content aufbauen: P01-Kontext + optionales Transkript
        p01_context = json.dumps(p01_payload, ensure_ascii=False)
        user_content = (
            loaded.user_prompt_template
            + f"\n\n<kundenkontext_p01>{p01_context}</kundenkontext_p01>"
        )
        if transcript:
            user_content += f"\n<transkript>{transcript}</transkript>"

        res = call_pipeline_llm(
            prompt_key="P04",
            system_prompt=loaded.system_prompt,
            user_content=user_content,
            tenant_id=tenant_id,
        )

        raw_text = res.text
        input_tokens = res.input_tokens if res.input_tokens > 0 else 3000
        output_tokens = res.output_tokens if res.output_tokens > 0 else 1500
        cache_read = res.cache_read_tokens
        actual_cost = res.cost_usd
        model_id = res.model_id
        logger.info("p04 run_id=%s cache_read_tokens=%s", run_id, cache_read)
        logger.debug("p04 run_id=%s: LLM-Antwort erhalten (%d Zeichen)", run_id, len(raw_text))

        # ------------------------------------------------------------------
        # 5. JSON-Parsing (mit Retry). [HYPOTHESE]-Strings werden NICHT gefiltert.
        # ------------------------------------------------------------------
        try:
            output_json = _extract_json_from_text(raw_text)
        except json.JSONDecodeError as first_err:
            logger.warning(
                "p04 run_id=%s: JSON-Parsing fehlgeschlagen (%s), Retry mit Schema-Reminder",
                run_id,
                first_err,
            )
            # Felder = Louis' kanonische P04-Top-Level-Keys (content-truth/schemas/p04).
            schema_hint = (
                "\n\nDeine Antwort MUSS als reines JSON-Objekt ohne Markdown-Formatierung "
                "ausgegeben werden. Pflicht-Top-Level-Felder: identitaet, innenwelt, "
                "wunschbild, content_trigger, sprache_der_zielgruppe, alltagsszenen, "
                "blockaden, ausloesemoment, _meta."
            )
            retry_res = call_pipeline_llm(
                prompt_key="P04",
                system_prompt=loaded.system_prompt,
                user_content=user_content + schema_hint,
                tenant_id=tenant_id,
            )
            raw_text = retry_res.text
            # Tokens und Kosten beider Calls summieren
            input_tokens += retry_res.input_tokens
            output_tokens += retry_res.output_tokens
            actual_cost += retry_res.cost_usd
            try:
                output_json = _extract_json_from_text(raw_text)
            except json.JSONDecodeError as retry_err:
                raise ValueError(
                    f"JSON-Parsing auch nach Retry fehlgeschlagen: {retry_err}"
                ) from retry_err

        # ------------------------------------------------------------------
        # 6. Kanonisches _meta absichern + gegen Louis-Schema validieren.
        # Soft-Fail: Schema-Verstoesse als _meta.luecken statt Hard-Fail.
        # ------------------------------------------------------------------
        avatar_row_id = str(uuid.uuid4())
        tenant_name, agentur_id = fetch_tenant_meta(tenant_id)
        llm_meta = output_json.get("_meta") if isinstance(output_json.get("_meta"), dict) else None
        canonical_meta = build_canonical_meta(
            "p04",
            tenant_id=tenant_id,
            model=model_id,
            generated_at=now_iso(),
            tenant_name=tenant_name,
            agentur_id=agentur_id,
            row_id=avatar_row_id,
            token_usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
            llm_meta=llm_meta,
        )
        output_json, schema_errors = finalize_canonical("p04", output_json, meta=canonical_meta)
        if schema_errors:
            logger.warning(
                "p04 run_id=%s: %d kanonische Schema-Luecke(n) in _meta.luecken dokumentiert",
                run_id,
                len(schema_errors),
            )

        # ------------------------------------------------------------------
        # 7. DB-Insert: tenant_audience_avatar (kanonischer Payload inkl. _meta)
        # ------------------------------------------------------------------
        output_hash = hashlib.sha256(json.dumps(output_json, sort_keys=True).encode()).hexdigest()

        with sync_session_factory() as session:
            row = session.execute(
                text(
                    "SELECT COALESCE(MAX(version), 0) FROM tenant_audience_avatar "
                    "WHERE tenant_id = :tenant_id"
                ),
                {"tenant_id": tenant_id},
            ).scalar()
            next_version = int(row) + 1

            session.execute(
                text(
                    "INSERT INTO tenant_audience_avatar "
                    "(id, tenant_id, version, is_active, source, payload, "
                    "prompt_version_hash, model_id, project_id, created_at) "
                    "VALUES (:id, :tenant_id, :version, false, 'transcript', "
                    "CAST(:payload AS jsonb), :prompt_version_hash, :model_id, :project_id, now())"
                ),
                {
                    "id": avatar_row_id,
                    "tenant_id": tenant_id,
                    "version": next_version,
                    "payload": json.dumps(output_json, ensure_ascii=False),
                    "prompt_version_hash": prompt_version_hash,
                    "model_id": model_id,
                    "project_id": project_id,
                },
            )
            session.commit()
        logger.info(
            "p04 run_id=%s tenant=%s: audience_avatar version=%d inserted",
            run_id,
            tenant_id,
            next_version,
        )

        # ------------------------------------------------------------------
        # 7. Actual-Cost in daily_cost_tenant schreiben
        # ------------------------------------------------------------------
        try:
            asyncio.run(_record_actual_cost(tenant_id, actual_cost))
        except Exception as cost_err:
            logger.warning(
                "p04 run_id=%s: actual-cost recording fehlgeschlagen: %s", run_id, cost_err
            )

        # ------------------------------------------------------------------
        # 7b. Audit-Update: setup_pipeline_run auf 'done' setzen
        # ------------------------------------------------------------------
        duration_ms = int((time.monotonic() - start_ts) * 1000)
        with sync_session_factory() as session:
            session.execute(
                text(
                    "UPDATE setup_pipeline_run SET "
                    "status='done', "
                    "model_id=:model_id, "
                    "input_tokens=:input_tokens, "
                    "output_tokens=:output_tokens, "
                    "cost_usd=:cost_usd, "
                    "duration_ms=:duration_ms, "
                    "output_hash=:output_hash, "
                    "prompt_version_hash=:prompt_version_hash, "
                    "finished_at=now() "
                    "WHERE id=:id"
                ),
                {
                    "id": run_id,
                    "model_id": model_id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": actual_cost,
                    "duration_ms": duration_ms,
                    "output_hash": output_hash,
                    "prompt_version_hash": prompt_version_hash,
                },
            )
            session.commit()
        logger.info(
            "p04 run_id=%s: done in %dms, cost=%.6f USD, output_hash=%s",
            run_id,
            duration_ms,
            actual_cost,
            output_hash[:16],
        )

        # ------------------------------------------------------------------
        # 8. Return
        # ------------------------------------------------------------------
        return {"run_id": run_id, "status": "done"}

    except BudgetExceededError:
        # BUG-1-Fix: Router-Budget überschritten (HTTP 412) aus call_pipeline_llm → paused_for_cost
        logger.warning(
            "p04 run_id=%s tenant=%s: Router-Budget überschritten (412), pausing", run_id, tenant_id
        )
        try:
            with sync_session_factory() as session:
                session.execute(
                    text(
                        "UPDATE setup_pipeline_run SET status='paused_for_cost', "
                        "finished_at=now() WHERE id=:id"
                    ),
                    {"id": run_id},
                )
                session.commit()
        except Exception as db_err:
            logger.error(
                "p04 run_id=%s: DB-Update (paused_for_cost) fehlgeschlagen: %s", run_id, db_err
            )
        return {"run_id": run_id, "status": "paused_for_cost"}

    except Exception as exc:
        logger.exception("p04 run_id=%s tenant=%s: FAILED — %s", run_id, tenant_id, exc)
        try:
            with sync_session_factory() as session:
                session.execute(
                    text(
                        "UPDATE setup_pipeline_run SET "
                        "status='failed', "
                        "error_meta=CAST(:error_meta AS jsonb) "
                        "WHERE id=:id"
                    ),
                    {
                        "id": run_id,
                        "error_meta": json.dumps({"error": str(exc)}),
                    },
                )
                session.commit()
        except Exception as db_err:
            logger.error("p04 run_id=%s: Fehler beim DB-Update auf 'failed': %s", run_id, db_err)
        return {"run_id": run_id, "status": "failed", "error": str(exc)}
