"""
P01-Service — Kundenkontext-Extraktion aus Transkript + Mini-Formular.

Workflow:
1. Setup-Pipeline-Run in DB anlegen (status='running')
2. Tageskosten-Cap prüfen (CostCapMiddleware, async via asyncio.run)
3. Prompt laden (PromptLoader, sync via Nextcloud)
4. Vertex/Gemini-Call via google-generativeai (sync)
5. JSON-Parsing + Schema-Validierung (jsonschema)
6. Insert in tenant_customer_context
7. Audit-Update in setup_pipeline_run (status='done')
"""
import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import jsonschema
from sqlalchemy import text

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from services.prompt_loader import get_default_prompt_loader

logger = logging.getLogger(__name__)

VERTEX_MODEL_ID = "gemini-2.5-flash-lite-preview-06-17"  # dated alias, gepinnt

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "../schemas/p01_output_schema.json")


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _load_output_schema() -> dict:
    with open(_SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _extract_json_from_text(raw: str) -> dict:
    """JSON aus dem LLM-Output parsen — entfernt Markdown-Code-Zaun falls vorhanden."""
    cleaned = raw.strip()
    # Markdown-Code-Block entfernen (```json ... ``` oder ``` ... ```)
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # erste Zeile (```json) und letzte Zeile (```) entfernen
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
    """Actual-Cost nach erfolgreichem Gemini-Call ins daily_cost_tenant schreiben."""
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

@celery_app.task(name="tasks.p01_task.run_p01", bind=True, max_retries=2)
def run_p01(self, tenant_id: str, transcript: str, mini_form_data: dict = None) -> dict:
    """P01-Extraktion: Kundenkontext aus Transkript + optionalem Mini-Formular.

    Args:
        tenant_id:      ID des Tenants (z.B. UUID-String)
        transcript:     Volltext des Transkripts
        mini_form_data: Optionales Dict mit Formular-Eingaben

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
    # 1. Setup-Pipeline-Run anlegen
    # ------------------------------------------------------------------
    with sync_session_factory() as session:
        session.execute(
            text(
                "INSERT INTO setup_pipeline_run (id, tenant_id, stage, status, created_at) "
                "VALUES (:id, :tenant_id, 'p01', 'running', now())"
            ),
            {"id": run_id, "tenant_id": tenant_id},
        )
        session.commit()
    logger.info("p01 run_id=%s tenant=%s: pipeline run created", run_id, tenant_id)

    try:
        # ------------------------------------------------------------------
        # 2. Cost-Cap prüfen (estimated: ~2000 input + 1000 output tokens)
        # ------------------------------------------------------------------
        from services.cost_cap import CostCapExceeded, estimate_vertex_cost

        estimated_cost = estimate_vertex_cost(VERTEX_MODEL_ID, 2000, 1000)
        try:
            asyncio.run(_run_cost_check(tenant_id, estimated_cost))
        except CostCapExceeded:
            logger.warning(
                "p01 run_id=%s tenant=%s: daily cost cap exceeded, pausing",
                run_id, tenant_id,
            )
            with sync_session_factory() as session:
                session.execute(
                    text(
                        "UPDATE setup_pipeline_run SET status='paused_for_cost', "
                        "finished_at=now() WHERE id=:id"
                    ),
                    {"id": run_id},
                )
                session.commit()
            return {"run_id": run_id, "status": "paused_for_cost"}

        # ------------------------------------------------------------------
        # 3. Prompt laden (sync)
        # ------------------------------------------------------------------
        loader = get_default_prompt_loader()
        loaded = loader.load("P01")
        prompt_version_hash = loaded.sha
        system_prompt_text = loaded.system_prompt
        user_prompt_text = loaded.user_prompt_template
        logger.debug(
            "p01 run_id=%s: prompt sha=%s geladen", run_id, prompt_version_hash[:12]
        )

        # ------------------------------------------------------------------
        # 4. Vertex-Call (sync — google-generativeai)
        # ------------------------------------------------------------------
        import google.generativeai as genai
        from config import settings

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(
            model_name=VERTEX_MODEL_ID,
            system_instruction=system_prompt_text,
        )

        user_content = (
            f"{user_prompt_text}\n\n"
            f"<transkript>{transcript}</transkript>"
        )
        if mini_form_data:
            user_content += (
                f"\n<formular>{json.dumps(mini_form_data, ensure_ascii=False)}</formular>"
            )

        response = model.generate_content(user_content)
        raw_text = response.text
        logger.debug("p01 run_id=%s: Gemini-Antwort erhalten (%d Zeichen)", run_id, len(raw_text))

        # Token-Nutzung auslesen (best-effort)
        try:
            usage_meta = response.usage_metadata
            input_tokens = usage_meta.prompt_token_count or 2000
            output_tokens = usage_meta.candidates_token_count or 1000
        except Exception:
            input_tokens, output_tokens = 2000, 1000

        actual_cost = estimate_vertex_cost(VERTEX_MODEL_ID, input_tokens, output_tokens)

        # ------------------------------------------------------------------
        # 5. JSON-Parsing + Schema-Validierung
        # ------------------------------------------------------------------
        schema = _load_output_schema()

        try:
            output_json = _extract_json_from_text(raw_text)
        except json.JSONDecodeError as first_err:
            logger.warning(
                "p01 run_id=%s: JSON-Parsing fehlgeschlagen (%s), Retry mit Schema-Reminder",
                run_id, first_err,
            )
            # Retry: Schema-Reminder an Model anhängen
            schema_hint = (
                "\n\nDeine Antwort MUSS als reines JSON-Objekt ohne Markdown-Formatierung "
                "ausgegeben werden. Pflichtfelder: "
                "unternehmensgeschichte, kernbotschaft, zielgruppe, expertise, werte."
            )
            retry_response = model.generate_content(user_content + schema_hint)
            raw_text = retry_response.text
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
                "p01 run_id=%s: Schema-Validierung fehlgeschlagen: %s", run_id, ve.message
            )
            # Weich-Fehler: Wir loggen, brechen aber nicht ab — Felder werden ggf. mit None gefüllt
            # (wunschzustand + innenwelt werden sowieso überschrieben)

        # ------------------------------------------------------------------
        # 6. Wunschzustand + Innenwelt erzwingend auf null setzen
        # ------------------------------------------------------------------
        output_json["wunschzustand"] = None
        output_json["innenwelt"] = None

        # ------------------------------------------------------------------
        # 7. DB-Insert: tenant_customer_context
        # ------------------------------------------------------------------
        output_hash = hashlib.sha256(
            json.dumps(output_json, sort_keys=True).encode()
        ).hexdigest()

        with sync_session_factory() as session:
            row = session.execute(
                text(
                    "SELECT COALESCE(MAX(version), 0) FROM tenant_customer_context "
                    "WHERE tenant_id = :tenant_id"
                ),
                {"tenant_id": tenant_id},
            ).scalar()
            next_version = int(row) + 1

            session.execute(
                text(
                    "INSERT INTO tenant_customer_context "
                    "(id, tenant_id, version, is_active, source, payload, "
                    "prompt_version_hash, model_id, created_at) "
                    "VALUES (:id, :tenant_id, :version, false, 'transcript', "
                    ":payload::jsonb, :prompt_version_hash, :model_id, now())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "version": next_version,
                    "payload": json.dumps(output_json, ensure_ascii=False),
                    "prompt_version_hash": prompt_version_hash,
                    "model_id": VERTEX_MODEL_ID,
                },
            )
            session.commit()
        logger.info(
            "p01 run_id=%s tenant=%s: customer_context version=%d inserted",
            run_id, tenant_id, next_version,
        )

        # ------------------------------------------------------------------
        # 8. Actual-Cost in daily_cost_tenant schreiben
        # ------------------------------------------------------------------
        try:
            asyncio.run(_record_actual_cost(tenant_id, actual_cost))
        except Exception as cost_err:
            logger.warning("p01 run_id=%s: actual-cost recording fehlgeschlagen: %s", run_id, cost_err)

        # ------------------------------------------------------------------
        # 8b. Audit-Update: setup_pipeline_run auf 'done' setzen
        # ------------------------------------------------------------------
        duration_ms = int((time.monotonic() - start_ts) * 1000)
        with sync_session_factory() as session:
            session.execute(
                text(
                    "UPDATE setup_pipeline_run SET "
                    "status='done', "
                    "input_tokens=:input_tokens, "
                    "output_tokens=:output_tokens, "
                    "cost_usd=:cost_usd, "
                    "duration_ms=:duration_ms, "
                    "output_hash=:output_hash, "
                    "prompt_version_hash=:prompt_version_hash, "
                    "model_id=:model_id, "
                    "finished_at=now() "
                    "WHERE id=:id"
                ),
                {
                    "id": run_id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": actual_cost,
                    "duration_ms": duration_ms,
                    "output_hash": output_hash,
                    "prompt_version_hash": prompt_version_hash,
                    "model_id": VERTEX_MODEL_ID,
                },
            )
            session.commit()
        logger.info(
            "p01 run_id=%s: done in %dms, cost=%.6f USD, output_hash=%s",
            run_id, duration_ms, actual_cost, output_hash[:16],
        )

        # ------------------------------------------------------------------
        # 9. Return
        # ------------------------------------------------------------------
        return {"run_id": run_id, "status": "done", "p01_run_id": run_id}

    except Exception as exc:
        logger.exception("p01 run_id=%s tenant=%s: FAILED — %s", run_id, tenant_id, exc)
        try:
            with sync_session_factory() as session:
                session.execute(
                    text(
                        "UPDATE setup_pipeline_run SET "
                        "status='failed', "
                        "error_meta=:error_meta::jsonb, "
                        "finished_at=now() "
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
                "p01 run_id=%s: Fehler beim DB-Update auf 'failed': %s", run_id, db_err
            )
        return {"run_id": run_id, "status": "failed", "error": str(exc)}
