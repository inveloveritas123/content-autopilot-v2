"""
P12b-Task — Lektor-Pass mit "frischen Augen".

Workflow:
1. Input-Validierung (Pflichtfelder aus P12-Output prüfen)
2. Defensives Pruning von Voice + Avatar auf stilistische Felder
3. Cost-Cap prüfen
4. Prompt laden (P12b)
5. User-Prompt aus gepruntetem Kontext bauen
6. Anthropic-Call mit cache_control ephemeral auf System-Prompt
7. Token-Usage tracken
8. JSON-Parsing
9. Schema-Validierung gegen p12b_output_schema.json
10. Loop-Schutz: bei "zurueck_an_p12" + loop_iteration >= 1 → loop_break
11. Reviewer-Queue-Eintrag bei loop_break
12. Return dict
"""
import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import anthropic
import jsonschema
from sqlalchemy import text

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from services.prompt_loader import get_default_prompt_loader

logger = logging.getLogger(__name__)

ANTHROPIC_MODEL_ID = "claude-sonnet-4-6-20251022"
ANTHROPIC_PRICING_KEY = "claude-sonnet-4-6"

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "schemas", "p12b_output_schema.json")


# ---------------------------------------------------------------------------
# Input-Dataclasses (Trennschnitt-Enforcement)
# ---------------------------------------------------------------------------

@dataclass
class P12Input:
    """Strikt begrenzte Inputs für P12b — kein Zugriff auf Ideen/Antworten/Voll-Profile."""
    post: str
    alternative_opener: list
    design_notizen: str
    ki_signal_check: dict
    potenzielle_schwaechen: list


@dataclass
class P12bContext:
    """Gekürzter Voice+Avatar-Kontext für Lektor."""
    voice_pruned: dict   # nur stilistische Felder
    avatar_pruned: dict  # nur Zielgruppen-Sprache


# ---------------------------------------------------------------------------
# Pruning-Konstanten
# ---------------------------------------------------------------------------

VOICE_KEYS_FOR_P12B = [
    "grundton",
    "satzarchitektur",
    "verbotene_woerter",
    "intensitaetsmarker",
    "persoenlichkeits_stance",
    "vermeidungsprofil",
]

AVATAR_KEYS_FOR_P12B = ["sprache_der_zielgruppe", "content_trigger"]

# Pflichtfelder im P12-Output
_P12_REQUIRED_FIELDS = {"post", "alternative_opener", "design_notizen", "ki_signal_check", "potenzielle_schwaechen"}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _load_schema() -> dict:
    with open(os.path.normpath(_SCHEMA_PATH), "r", encoding="utf-8") as f:
        return json.load(f)


_P12B_SCHEMA = _load_schema()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _parse_json_from_text(raw: str) -> dict:
    """Extrahiert JSON aus dem LLM-Output — entfernt Markdown-Fencing falls vorhanden."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for fence in ("```json", "```"):
        if fence in raw:
            start = raw.index(fence) + len(fence)
            end = raw.find("```", start)
            if end != -1:
                candidate = raw[start:end].strip()
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
    raise ValueError(f"Konnte kein JSON aus LLM-Output extrahieren. Anfang: {raw[:200]!r}")


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


async def _record_actual_cost(tenant_id: str, actual_cost: float) -> None:
    """Schreibt die tatsächlichen Kosten nach erfolgreichem Anthropic-Call."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as async_sm
    from config import settings
    from services.cost_cap import CostCapMiddleware

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    AsyncSessionLocal = async_sm(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with AsyncSessionLocal() as session:
            mw = CostCapMiddleware(session)
            await mw.check_and_record(tenant_id, 0.0, actual_cost_usd=actual_cost)
    finally:
        await engine.dispose()


def _insert_reviewer_queue(tenant_id: str, p12_output: dict) -> None:
    """Versucht einen Loop-Break-Eintrag in telegram_message_log zu schreiben."""
    try:
        with sync_session_factory() as session:
            session.execute(
                text(
                    "INSERT INTO telegram_message_log "
                    "(id, tenant_id, direction, content, routed_to, created_at) "
                    "VALUES (:id, :tenant_id, 'system', :content, 'reviewer_queue', now())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "content": json.dumps(
                        {
                            "reason": "p12b_loop_break",
                            "post": p12_output.get("post", "")[:200],
                        }
                    ),
                    "routed_to": "reviewer_queue",
                },
            )
            session.commit()
    except Exception as e:
        logger.warning("p12b: reviewer_queue insert fehlgeschlagen: %s", e)


# ---------------------------------------------------------------------------
# Celery Task
# ---------------------------------------------------------------------------

@celery_app.task(name="tasks.p12b_task.run_p12b", bind=True, max_retries=1)
def run_p12b(
    self,
    tenant_id: str,
    p12_output: dict,        # muss P12Input-Felder enthalten
    voice_payload: dict,     # MUSS bereits geprunt sein (Caller-Verantwortung)
    avatar_payload: dict,    # MUSS bereits geprunt sein
    loop_iteration: int = 0,
) -> dict:
    """P12b Lektor-Pass: prüft P12-Output mit frischen Augen und optimiert oder weist zurück.

    Args:
        tenant_id:      ID des Tenants (UUID-String).
        p12_output:     Output-Dict von P12 (post, alternative_opener, design_notizen,
                        ki_signal_check, potenzielle_schwaechen).
        voice_payload:  Voice-Profil-Dict (wird intern zusätzlich defensiv geprunt).
        avatar_payload: Audience-Avatar-Dict (wird intern zusätzlich defensiv geprunt).
        loop_iteration: Anzahl bisheriger P12b-Zyklen (Loop-Schutz).

    Returns:
        {"status": "done"|"needs_revision"|"loop_break"|"paused_for_cost"|"failed", ...}
    """
    from services.kill_switch import check_kill_switch, KillSwitchTriggered
    try:
        check_kill_switch(tenant_id)
    except KillSwitchTriggered:
        return {"status": "aborted", "reason": "tenant_disabled"}
    run_id = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # 1. Input-Validierung
    # ------------------------------------------------------------------
    missing = _P12_REQUIRED_FIELDS - set(p12_output.keys())
    if missing:
        logger.error("p12b run_id=%s: ungültiger P12-Output, fehlende Felder: %s", run_id, missing)
        return {"status": "failed", "error": "Ungültiger P12-Output", "missing_fields": list(missing)}

    # ------------------------------------------------------------------
    # Setup-Pipeline-Run anlegen
    # ------------------------------------------------------------------
    with sync_session_factory() as session:
        try:
            session.execute(
                text(
                    "INSERT INTO setup_pipeline_run "
                    "(id, tenant_id, stage, model_id, status) "
                    "VALUES (:id, :tenant_id, 'p12b', :model_id, 'running')"
                ),
                {"id": run_id, "tenant_id": tenant_id, "model_id": ANTHROPIC_MODEL_ID},
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("p12b run_id=%s: failed to create setup_pipeline_run: %s", run_id, exc)
            raise

    logger.info(
        "p12b run_id=%s tenant=%s loop_iteration=%d: pipeline run created",
        run_id,
        tenant_id,
        loop_iteration,
    )

    t_start = time.monotonic()

    try:
        # ------------------------------------------------------------------
        # 2. Defensives Pruning (auch wenn Caller schon geprunt hat)
        # ------------------------------------------------------------------
        voice_pruned = {k: voice_payload[k] for k in VOICE_KEYS_FOR_P12B if k in voice_payload}
        avatar_pruned = {k: avatar_payload[k] for k in AVATAR_KEYS_FOR_P12B if k in avatar_payload}
        logger.debug(
            "p12b run_id=%s: pruned keys — voice=%d avatar=%d",
            run_id,
            len(voice_pruned),
            len(avatar_pruned),
        )

        # ------------------------------------------------------------------
        # 3. Cost-Cap prüfen
        # ------------------------------------------------------------------
        from services.cost_cap import CostCapExceeded, estimate_anthropic_cost

        estimated_cost = estimate_anthropic_cost(ANTHROPIC_PRICING_KEY, 2000, 800)
        logger.info("p12b run_id=%s: estimated cost=%.6f USD", run_id, estimated_cost)

        try:
            asyncio.run(_run_cost_check(tenant_id, estimated_cost))
        except CostCapExceeded:
            logger.warning(
                "p12b run_id=%s tenant=%s: daily cost cap exceeded, pausing",
                run_id,
                tenant_id,
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
        # 4. Prompt laden
        # ------------------------------------------------------------------
        loader = get_default_prompt_loader()
        loaded = loader.load("P12b")
        prompt_version_hash = loaded.sha
        logger.debug("p12b run_id=%s: prompt sha=%s geladen", run_id, prompt_version_hash[:12])

        # ------------------------------------------------------------------
        # 5. User-Prompt bauen
        # ------------------------------------------------------------------
        user_payload = {
            "p12_output": {
                "post": p12_output["post"],
                "alternative_opener": p12_output["alternative_opener"],
                "design_notizen": p12_output["design_notizen"],
                "ki_signal_check": p12_output["ki_signal_check"],
                "potenzielle_schwaechen": p12_output["potenzielle_schwaechen"],
            },
            "voice_stil": voice_pruned,
            "zielgruppen_sprache": avatar_pruned,
        }
        context_json_str = json.dumps(user_payload, ensure_ascii=False)

        if "{context_json}" in loaded.user_prompt_template:
            user_prompt = loaded.user_prompt_template.replace("{context_json}", context_json_str)
        else:
            user_prompt = loaded.user_prompt_template + "\n\n" + context_json_str

        # ------------------------------------------------------------------
        # 6. Anthropic-Call mit cache_control ephemeral auf System-Prompt
        # ------------------------------------------------------------------
        from config import settings

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        model_id = os.environ.get("BACKTEST_MODEL_OVERRIDE") or ANTHROPIC_MODEL_ID
        response = client.messages.create(
            model=model_id,
            max_tokens=2000,
            system=[
                {
                    "type": "text",
                    "text": loaded.system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = response.content[0].text
        logger.debug("p12b run_id=%s: Anthropic-Antwort erhalten (%d Zeichen)", run_id, len(raw_text))

        # ------------------------------------------------------------------
        # 7. Token-Usage tracken
        # ------------------------------------------------------------------
        usage = response.usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_read = getattr(usage, "cache_read_input_tokens", 0)
        logger.info(
            "p12b run_id=%s: usage input=%d output=%d cache_read=%d tenant=%s",
            run_id,
            input_tokens,
            output_tokens,
            cache_read,
            tenant_id,
        )

        actual_cost = estimate_anthropic_cost(ANTHROPIC_PRICING_KEY, input_tokens, output_tokens)

        # ------------------------------------------------------------------
        # 8. JSON-Parsing
        # ------------------------------------------------------------------
        try:
            output_json = _parse_json_from_text(raw_text)
        except ValueError as parse_err:
            raise ValueError(f"p12b JSON-Parsing fehlgeschlagen: {parse_err}") from parse_err

        # ------------------------------------------------------------------
        # 9. Schema-Validierung
        # ------------------------------------------------------------------
        try:
            jsonschema.validate(instance=output_json, schema=_P12B_SCHEMA)
        except jsonschema.ValidationError as ve:
            logger.warning(
                "p12b run_id=%s: Schema-Validierung fehlgeschlagen: %s", run_id, ve.message
            )

        # ------------------------------------------------------------------
        # 10. Loop-Schutz
        # ------------------------------------------------------------------
        decision = output_json.get("decision", "")

        if decision == "zurueck_an_p12" and loop_iteration >= 1:
            logger.warning(
                "p12b: Loop-Limit erreicht (iteration=%d), liefere Original aus",
                loop_iteration,
            )
            _insert_reviewer_queue(tenant_id, p12_output)

            _finalize_run(
                run_id=run_id,
                t_start=t_start,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                actual_cost=actual_cost,
                prompt_version_hash=prompt_version_hash,
                output_hash="loop_break",
                status="done",
            )
            return {
                "run_id": run_id,
                "status": "loop_break",
                "final_post": p12_output["post"],
                "reason": "loop_limit_reached",
            }

        # ------------------------------------------------------------------
        # Actual-Cost aufzeichnen
        # ------------------------------------------------------------------
        try:
            asyncio.run(_record_actual_cost(tenant_id, actual_cost))
        except Exception as cost_err:
            logger.warning("p12b run_id=%s: actual-cost recording fehlgeschlagen: %s", run_id, cost_err)

        # ------------------------------------------------------------------
        # 11. Audit-Update und Return
        # ------------------------------------------------------------------
        import hashlib
        output_hash = hashlib.sha256(
            json.dumps(output_json, sort_keys=True).encode()
        ).hexdigest()

        _finalize_run(
            run_id=run_id,
            t_start=t_start,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            actual_cost=actual_cost,
            prompt_version_hash=prompt_version_hash,
            output_hash=output_hash,
            status="done",
        )

        if decision == "optimiert":
            logger.info(
                "p12b run_id=%s: decision=optimiert, final_post Länge=%d",
                run_id,
                len(output_json.get("optimierter_post", "")),
            )
            return {
                "run_id": run_id,
                "status": "done",
                "decision": "optimiert",
                "final_post": output_json.get("optimierter_post", p12_output["post"]),
                "begruendung": output_json.get("begruendung", ""),
                "content_metadata": {
                    "telegram_approval_hint": "Bitte gib diesen Post in der App frei, bevor er auf LinkedIn veröffentlicht wird.",
                },
            }

        # decision == "zurueck_an_p12" (und loop_iteration == 0)
        logger.info(
            "p12b run_id=%s: decision=zurueck_an_p12, loop_iteration=%d",
            run_id,
            loop_iteration,
        )
        return {
            "run_id": run_id,
            "status": "needs_revision",
            "decision": "zurueck_an_p12",
            "richtung_fuer_p12": output_json.get("richtung_fuer_p12", ""),
            "loop_iteration": loop_iteration,
        }

    except Exception as exc:
        duration_ms = int((time.monotonic() - t_start) * 1000)
        logger.error("p12b run_id=%s tenant=%s: FAILED — %s", run_id, tenant_id, exc, exc_info=True)

        try:
            with sync_session_factory() as session:
                session.execute(
                    text(
                        "UPDATE setup_pipeline_run SET "
                        "status = 'failed', "
                        "error_meta = :error_meta, "
                        "duration_ms = :duration_ms, "
                        "finished_at = now() "
                        "WHERE id = :run_id"
                    ),
                    {
                        "run_id": run_id,
                        "error_meta": json.dumps(
                            {"error": type(exc).__name__, "message": str(exc)}
                        ),
                        "duration_ms": duration_ms,
                    },
                )
                session.commit()
        except Exception as audit_exc:
            logger.error(
                "p12b run_id=%s: Fehler beim Audit-Update auf 'failed': %s", run_id, audit_exc
            )

        return {"status": "failed", "error": str(exc)}


# ---------------------------------------------------------------------------
# Interner Helfer: Audit-Update auf 'done'
# ---------------------------------------------------------------------------

def _finalize_run(
    run_id: str,
    t_start: float,
    input_tokens: int,
    output_tokens: int,
    actual_cost: float,
    prompt_version_hash: str,
    output_hash: str,
    status: str = "done",
) -> None:
    duration_ms = int((time.monotonic() - t_start) * 1000)
    try:
        with sync_session_factory() as session:
            session.execute(
                text(
                    "UPDATE setup_pipeline_run SET "
                    "status = :status, "
                    "input_tokens = :input_tokens, "
                    "output_tokens = :output_tokens, "
                    "cost_usd = :cost_usd, "
                    "duration_ms = :duration_ms, "
                    "output_hash = :output_hash, "
                    "prompt_version_hash = :prompt_version_hash, "
                    "finished_at = now() "
                    "WHERE id = :run_id"
                ),
                {
                    "run_id": run_id,
                    "status": status,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": str(actual_cost),
                    "duration_ms": duration_ms,
                    "output_hash": output_hash,
                    "prompt_version_hash": prompt_version_hash,
                },
            )
            session.commit()
    except Exception as exc:
        logger.error("p12b run_id=%s: Fehler beim finalize_run: %s", run_id, exc)
