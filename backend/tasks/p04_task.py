"""
P04-Service — Audience-Avatar-Vertiefung aus P01-Kundenkontext.

Workflow:
1. Setup-Pipeline-Run in DB anlegen (status='running')
2. Tageskosten-Cap prüfen (CostCapMiddleware, async via asyncio.run)
3. Prompt laden (PromptLoader, sync via Nextcloud)
4. Anthropic-Call mit cache_control: ephemeral auf System-Prompt
5. JSON-Parsing + Schema-Validierung (jsonschema)
   [HYPOTHESE]-Markierungen werden NICHT gefiltert — durchgereicht wie empfangen.
6. Insert in tenant_audience_avatar (is_active=False)
7. Audit-Update in setup_pipeline_run (status='done')
"""
import asyncio
import hashlib
import json
import logging
import os
import time
import uuid

import jsonschema
from sqlalchemy import text

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from services.prompt_loader import get_default_prompt_loader

logger = logging.getLogger(__name__)

ANTHROPIC_MODEL_ID = "claude-sonnet-4-6-20251022"  # dated alias

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "../schemas/p04_output_schema.json")


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _load_output_schema() -> dict:
    with open(_SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


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

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    AsyncSessionLocal = async_sm(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with AsyncSessionLocal() as session:
            mw = CostCapMiddleware(session)
            await mw.check_and_record(tenant_id, estimated_cost)
    finally:
        await engine.dispose()


async def _record_actual_cost(tenant_id: str, actual_cost: float) -> None:
    """Actual-Cost nach erfolgreichem Anthropic-Call ins daily_cost_tenant schreiben."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as async_sm
    from config import settings
    from services.cost_cap import CostCapMiddleware

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    AsyncSessionLocal = async_sm(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with AsyncSessionLocal() as session:
            mw = CostCapMiddleware(session)
            # estimated_cost=0 → nur record, kein double-check
            await mw.check_and_record(tenant_id, 0.0, actual_cost_usd=actual_cost)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Celery Task
# ---------------------------------------------------------------------------

@celery_app.task(name="tasks.p04_task.run_p04", bind=True, max_retries=2)
def run_p04(self, tenant_id: str, p01_payload: dict, transcript: str = None, project_id: str | None = None) -> dict:
    """P04-Avatar-Vertiefung: Psychologisches Audience-Avatar aus P01-Kontext.

    Args:
        tenant_id:   ID des Tenants (z.B. UUID-String)
        p01_payload: Pflicht — Output-Dict aus P01 (Kundenkontext)
        transcript:  Optional — Transkript-Text für zusätzlichen Kontext

    Returns:
        {"run_id": str, "status": "done"|"paused_for_cost"|"failed", "error": str|None}
    """
    from services.kill_switch import check_kill_switch, KillSwitchTriggered
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
        # 2. Cost-Cap prüfen (estimated: ~3000 input + 1500 output tokens)
        # ------------------------------------------------------------------
        from services.cost_cap import CostCapExceeded, estimate_anthropic_cost

        # Kurzname für Pricing-Lookup (ohne Datum-Suffix)
        _pricing_model_key = "claude-sonnet-4-6"
        estimated_cost = estimate_anthropic_cost(_pricing_model_key, 3000, 1500)
        try:
            asyncio.run(_run_cost_check(tenant_id, estimated_cost))
        except CostCapExceeded:
            logger.warning(
                "p04 run_id=%s tenant=%s: daily cost cap exceeded, pausing",
                run_id, tenant_id,
            )
            with sync_session_factory() as session:
                session.execute(
                    text(
                        "UPDATE setup_pipeline_run SET status='paused_for_cost' "
                        "WHERE id=:id"
                    ),
                    {"id": run_id},
                )
                session.commit()
            return {"run_id": run_id, "status": "paused_for_cost"}

        # ------------------------------------------------------------------
        # 3. Prompt laden (sync via Nextcloud)
        # ------------------------------------------------------------------
        loader = get_default_prompt_loader()
        loaded = loader.load("P04")
        prompt_version_hash = loaded.sha
        logger.debug(
            "p04 run_id=%s: prompt sha=%s geladen", run_id, prompt_version_hash[:12]
        )

        # ------------------------------------------------------------------
        # 4. Anthropic-Call mit cache_control: ephemeral auf System-Prompt
        # ------------------------------------------------------------------
        import anthropic
        from config import settings

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        # User-Content aufbauen: P01-Kontext + optionales Transkript
        p01_context = json.dumps(p01_payload, ensure_ascii=False)
        user_content = (
            loaded.user_prompt_template
            + f"\n\n<kundenkontext_p01>{p01_context}</kundenkontext_p01>"
        )
        if transcript:
            user_content += f"\n<transkript>{transcript}</transkript>"

        response = client.messages.create(
            model=ANTHROPIC_MODEL_ID,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": loaded.system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {"role": "user", "content": user_content}
            ],
        )

        raw_text = response.content[0].text
        logger.debug("p04 run_id=%s: Anthropic-Antwort erhalten (%d Zeichen)", run_id, len(raw_text))

        # Token-Nutzung auslesen (best-effort)
        try:
            usage = response.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            logger.info("p04 run_id=%s cache_read_input_tokens=%s", run_id, cache_read)
        except Exception:
            input_tokens, output_tokens, cache_read = 3000, 1500, 0

        # cache_read Tokens sind billiger (cache-Preis ~0.1x input), Schätzung: voller input-Preis
        actual_cost = estimate_anthropic_cost(_pricing_model_key, input_tokens, output_tokens)

        # ------------------------------------------------------------------
        # 5. JSON-Parsing + Schema-Validierung
        # [HYPOTHESE]-Strings werden NICHT gefiltert — einfach durchgereicht.
        # Das Schema verwendet additionalProperties:true und lässt null zu,
        # daher passieren [HYPOTHESE]-Markierungen die Validierung problemlos.
        # ------------------------------------------------------------------
        schema = _load_output_schema()

        try:
            output_json = _extract_json_from_text(raw_text)
        except json.JSONDecodeError as first_err:
            logger.warning(
                "p04 run_id=%s: JSON-Parsing fehlgeschlagen (%s), Retry mit Schema-Reminder",
                run_id, first_err,
            )
            schema_hint = (
                "\n\nDeine Antwort MUSS als reines JSON-Objekt ohne Markdown-Formatierung "
                "ausgegeben werden. Pflichtfelder: hauptperson, kernschmerzen, transformation."
            )
            retry_response = client.messages.create(
                model=ANTHROPIC_MODEL_ID,
                max_tokens=2048,
                system=[
                    {
                        "type": "text",
                        "text": loaded.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {"role": "user", "content": user_content + schema_hint}
                ],
            )
            raw_text = retry_response.content[0].text
            try:
                output_json = _extract_json_from_text(raw_text)
            except json.JSONDecodeError as retry_err:
                raise ValueError(
                    f"JSON-Parsing auch nach Retry fehlgeschlagen: {retry_err}"
                ) from retry_err

        try:
            jsonschema.validate(output_json, schema)
        except jsonschema.ValidationError as ve:
            logger.warning(
                "p04 run_id=%s: Schema-Validierung fehlgeschlagen: %s", run_id, ve.message
            )
            # Weich-Fehler: Wir loggen, brechen aber nicht ab

        # ------------------------------------------------------------------
        # 6. DB-Insert: tenant_audience_avatar (is_active=False)
        # ------------------------------------------------------------------
        output_hash = hashlib.sha256(
            json.dumps(output_json, sort_keys=True).encode()
        ).hexdigest()

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
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "version": next_version,
                    "payload": json.dumps(output_json, ensure_ascii=False),
                    "prompt_version_hash": prompt_version_hash,
                    "model_id": ANTHROPIC_MODEL_ID,
                    "project_id": project_id,
                },
            )
            session.commit()
        logger.info(
            "p04 run_id=%s tenant=%s: audience_avatar version=%d inserted",
            run_id, tenant_id, next_version,
        )

        # ------------------------------------------------------------------
        # 7. Actual-Cost in daily_cost_tenant schreiben
        # ------------------------------------------------------------------
        try:
            asyncio.run(_record_actual_cost(tenant_id, actual_cost))
        except Exception as cost_err:
            logger.warning("p04 run_id=%s: actual-cost recording fehlgeschlagen: %s", run_id, cost_err)

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
                    "model_id": ANTHROPIC_MODEL_ID,
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
            run_id, duration_ms, actual_cost, output_hash[:16],
        )

        # ------------------------------------------------------------------
        # 8. Return
        # ------------------------------------------------------------------
        return {"run_id": run_id, "status": "done"}

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
            logger.error(
                "p04 run_id=%s: Fehler beim DB-Update auf 'failed': %s", run_id, db_err
            )
        return {"run_id": run_id, "status": "failed", "error": str(exc)}
