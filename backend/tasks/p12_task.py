"""
P12-Task — Voice-basierter LinkedIn-Post-Generator.

Workflow:
1. Setup-Pipeline-Run anlegen (stage='p12', status='running')
2. Cost-Cap prüfen (CostCapMiddleware via asyncio.run)
3. Aktive Profile aus DB laden (customer_context, voice_profile, audience_avatar)
4. Profile auf P12-relevante Felder prunen
5. Prompt laden (PromptLoader, P12)
6. User-Prompt zusammenbauen
7. Anthropic-Call mit cache_control ephemeral auf System-Prompt
8. Token-Usage tracken (cache_read separat)
9. JSON-Parsing
10. Schema-Validierung gegen p12_output_schema.json
11. DB-Insert in content_pieces (idea_id als Referenz)
12. Audit-Update: setup_pipeline_run → 'done'
13. Return dict
"""
import asyncio
import hashlib
import json
import logging
import os
import time
import uuid

import anthropic
import jsonschema
from sqlalchemy import text

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from services.prompt_loader import get_default_prompt_loader

logger = logging.getLogger(__name__)

ANTHROPIC_MODEL_ID = "claude-sonnet-4-6-20251022"
ANTHROPIC_PRICING_KEY = "claude-sonnet-4-6"  # ohne Datum-Suffix für cost_cap.py

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "schemas", "p12_output_schema.json")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _load_schema() -> dict:
    with open(os.path.normpath(_SCHEMA_PATH), "r", encoding="utf-8") as f:
        return json.load(f)


_P12_SCHEMA = _load_schema()


# ---------------------------------------------------------------------------
# Pruning-Konstanten
# ---------------------------------------------------------------------------

VOICE_KEYS_FOR_P12 = [
    "grundton",
    "satzarchitektur",
    "signalwoerter",
    "fuellwoerter",
    "verbotene_woerter",
    "intensitaetsmarker",
    "erzaehlmuster",
    "emotionaler_ausdruck",
    "persoenlichkeits_stance",
    "emotionaler_subtext",
    "ueberzeugungsstil",
    "zielgruppen_sprachfilter",
    "vermeidungsprofil",
    "referenz_saetze",
]

CONTEXT_KEYS_FOR_P12 = [
    "person",
    "angebot",
    "positionierung",
    "kernbotschaft",
    "expertise",
]

AVATAR_KEYS_FOR_P12 = [
    "identitaet",
    "content_trigger",
    "sprache_der_zielgruppe",
]


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _load_active_profiles(tenant_id: str) -> tuple[dict, dict, dict]:
    """Lädt die aktiven Profile aus den 3 Setup-Tabellen.

    Gibt jeweils das payload-Dict zurück, oder ein leeres Dict wenn kein
    aktiver Eintrag gefunden wurde.
    """
    customer_context: dict = {}
    voice_profile: dict = {}
    audience_avatar: dict = {}

    with sync_session_factory() as session:
        row = session.execute(
            text(
                "SELECT payload FROM tenant_customer_context "
                "WHERE tenant_id = :t AND is_active = true "
                "ORDER BY version DESC LIMIT 1"
            ),
            {"t": tenant_id},
        ).fetchone()
        if row:
            customer_context = row.payload if isinstance(row.payload, dict) else json.loads(row.payload)

        row = session.execute(
            text(
                "SELECT payload FROM tenant_voice_profile "
                "WHERE tenant_id = :t AND is_active = true "
                "ORDER BY version DESC LIMIT 1"
            ),
            {"t": tenant_id},
        ).fetchone()
        if row:
            voice_profile = row.payload if isinstance(row.payload, dict) else json.loads(row.payload)

        row = session.execute(
            text(
                "SELECT payload FROM tenant_audience_avatar "
                "WHERE tenant_id = :t AND is_active = true "
                "ORDER BY version DESC LIMIT 1"
            ),
            {"t": tenant_id},
        ).fetchone()
        if row:
            audience_avatar = row.payload if isinstance(row.payload, dict) else json.loads(row.payload)

    logger.debug(
        "p12 _load_active_profiles tenant=%s: "
        "customer_context=%d keys, voice_profile=%d keys, audience_avatar=%d keys",
        tenant_id,
        len(customer_context),
        len(voice_profile),
        len(audience_avatar),
    )
    return customer_context, voice_profile, audience_avatar


def _prune_for_p12(
    customer_context: dict,
    voice_profile: dict,
    audience_avatar: dict,
) -> tuple[dict, dict, dict]:
    """Reduziert die Profile auf die für P12 relevanten Felder.

    Nur vorhandene Keys werden übernommen — kein KeyError bei fehlenden Feldern.
    """
    pruned_context = {k: customer_context[k] for k in CONTEXT_KEYS_FOR_P12 if k in customer_context}
    pruned_voice = {k: voice_profile[k] for k in VOICE_KEYS_FOR_P12 if k in voice_profile}
    pruned_avatar = {k: audience_avatar[k] for k in AVATAR_KEYS_FOR_P12 if k in audience_avatar}
    return pruned_context, pruned_voice, pruned_avatar


def _parse_json_from_text(raw: str) -> dict:
    """Extrahiert JSON aus dem LLM-Output — entfernt Markdown-Fencing falls vorhanden."""
    raw = raw.strip()
    # Direkter Parse-Versuch
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fenced code block: ```json ... ``` oder ``` ... ```
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


# ---------------------------------------------------------------------------
# Celery Task
# ---------------------------------------------------------------------------

@celery_app.task(name="tasks.p12_task.run_p12", bind=True, max_retries=2)
def run_p12(
    self,
    tenant_id: str,
    idea_id: str,
    answers: dict,
) -> dict:
    """P12 Voice-Post Generator: erzeugt LinkedIn-Post aus Voice-Profil + Kontext.

    Args:
        tenant_id: ID des Tenants (UUID-String).
        idea_id:   ID der zugehörigen Idee.
        answers:   Antworten des Unternehmers aus dem Fragebogen.

    Returns:
        {"run_id": str, "status": "done"|"paused_for_cost"|"failed",
         "p12_run_id": str, "output": dict}
    """
    run_id = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # 1. Setup-Pipeline-Run anlegen
    # ------------------------------------------------------------------
    with sync_session_factory() as session:
        try:
            session.execute(
                text(
                    "INSERT INTO setup_pipeline_run "
                    "(id, tenant_id, stage, model_id, status) "
                    "VALUES (:id, :tenant_id, 'p12', :model_id, 'running')"
                ),
                {"id": run_id, "tenant_id": tenant_id, "model_id": ANTHROPIC_MODEL_ID},
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("p12 run_id=%s: failed to create setup_pipeline_run: %s", run_id, exc)
            raise

    logger.info("p12 run_id=%s tenant=%s idea_id=%s: pipeline run created", run_id, tenant_id, idea_id)

    t_start = time.monotonic()

    try:
        # ------------------------------------------------------------------
        # 2. Cost-Cap prüfen
        # ------------------------------------------------------------------
        from services.cost_cap import CostCapExceeded, estimate_anthropic_cost

        estimated_cost = estimate_anthropic_cost(ANTHROPIC_PRICING_KEY, 3000, 1500)
        logger.info("p12 run_id=%s: estimated cost=%.6f USD", run_id, estimated_cost)

        try:
            asyncio.run(_run_cost_check(tenant_id, estimated_cost))
        except CostCapExceeded:
            logger.warning(
                "p12 run_id=%s tenant=%s: daily cost cap exceeded, pausing",
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
        # 3. Aktive Profile aus DB laden
        # ------------------------------------------------------------------
        customer_context, voice_profile, audience_avatar = _load_active_profiles(tenant_id)

        # ------------------------------------------------------------------
        # 4. Profile prunen
        # ------------------------------------------------------------------
        pruned_context, pruned_voice, pruned_avatar = _prune_for_p12(
            customer_context, voice_profile, audience_avatar
        )
        logger.debug(
            "p12 run_id=%s: pruned keys — context=%d voice=%d avatar=%d",
            run_id,
            len(pruned_context),
            len(pruned_voice),
            len(pruned_avatar),
        )

        # ------------------------------------------------------------------
        # 5. Prompt laden
        # ------------------------------------------------------------------
        loader = get_default_prompt_loader()
        loaded = loader.load("P12")
        prompt_version_hash = loaded.sha
        logger.debug("p12 run_id=%s: prompt sha=%s geladen", run_id, prompt_version_hash[:12])

        # ------------------------------------------------------------------
        # 6. User-Prompt zusammenbauen
        # ------------------------------------------------------------------
        context_payload = {
            "customer_context": pruned_context,
            "voice_profile": pruned_voice,
            "audience_avatar": pruned_avatar,
            "answers": answers,
            "idea_id": idea_id,
        }
        context_json_str = json.dumps(context_payload, ensure_ascii=False)
        user_prompt = loaded.user_prompt_template.replace(
            "{context_json}", context_json_str
        )

        # ------------------------------------------------------------------
        # 7. Anthropic-Call mit cache_control ephemeral auf System-Prompt
        # ------------------------------------------------------------------
        from config import settings

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        response = client.messages.create(
            model=ANTHROPIC_MODEL_ID,
            max_tokens=3000,
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
        logger.debug("p12 run_id=%s: Anthropic-Antwort erhalten (%d Zeichen)", run_id, len(raw_text))

        # ------------------------------------------------------------------
        # 8. Token-Usage tracken (cache_read NICHT zu input_tokens addieren)
        # ------------------------------------------------------------------
        usage = response.usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_read = getattr(usage, "cache_read_input_tokens", 0)
        logger.info(
            "p12 run_id=%s: usage input=%d output=%d cache_read=%d tenant=%s",
            run_id,
            input_tokens,
            output_tokens,
            cache_read,
            tenant_id,
        )

        actual_cost = estimate_anthropic_cost(ANTHROPIC_PRICING_KEY, input_tokens, output_tokens)

        # ------------------------------------------------------------------
        # 9. JSON-Parsing
        # ------------------------------------------------------------------
        try:
            output_json = _parse_json_from_text(raw_text)
        except ValueError as parse_err:
            raise ValueError(f"p12 JSON-Parsing fehlgeschlagen: {parse_err}") from parse_err

        # ------------------------------------------------------------------
        # 10. Schema-Validierung
        # ------------------------------------------------------------------
        try:
            jsonschema.validate(instance=output_json, schema=_P12_SCHEMA)
        except jsonschema.ValidationError as ve:
            logger.warning(
                "p12 run_id=%s: Schema-Validierung fehlgeschlagen: %s", run_id, ve.message
            )
            # Weich-Fehler: Wir loggen und fahren fort — Partial-Output ist besser als Abbruch

        # ------------------------------------------------------------------
        # 10b. Leerer-Post-Guard
        # ------------------------------------------------------------------
        post_text = output_json.get("post", "").strip()
        if not post_text:
            raise ValueError(
                "P12-Output hat kein 'post'-Feld oder es ist leer — LLM-Output abgelehnt"
            )

        # ------------------------------------------------------------------
        # 11. DB-Insert in content_pieces
        # ------------------------------------------------------------------
        # NOTE: content_pieces.source_item_id ist laut ORM NOT NULL (FK auf
        # source_items). P12 wird jedoch aus einer Idee (idea_id) generiert,
        # nicht aus einem SourceItem. Optionen:
        #   a) Schema-Migration: source_item_id nullable machen (empfohlen, TODO)
        #   b) Dummy-Verknüpfung über eine idea→source_item Relation (komplex)
        # Aktueller Workaround: source_item_id wird auf NULL gesetzt. Falls die
        # DB-Spalte tatsächlich NOT NULL ist, schlägt der Insert fehl und der
        # Task landet im 'failed'-Status. In diesem Fall ist eine Schema-
        # Migration nötig: ALTER TABLE content_pieces ALTER COLUMN
        # source_item_id DROP NOT NULL;
        # idea_id ist bereits als nullable FK auf content_ideas definiert.
        output_hash = hashlib.sha256(
            json.dumps(output_json, sort_keys=True).encode()
        ).hexdigest()

        content_piece_id = str(uuid.uuid4())
        with sync_session_factory() as session:
            try:
                session.execute(
                    text(
                        "INSERT INTO content_pieces "
                        "(id, tenant_id, idea_id, channel, content_text, content_metadata, status, created_at) "
                        "VALUES (:id, :tenant_id, :idea_id, 'linkedin', :content_text, "
                        ":content_metadata::jsonb, 'draft', now())"
                    ),
                    {
                        "id": content_piece_id,
                        "tenant_id": tenant_id,
                        "idea_id": idea_id,
                        "content_text": post_text,
                        "content_metadata": json.dumps(
                            {
                                "p12_run_id": run_id,
                                "alternative_opener": output_json.get("alternative_opener", []),
                                "design_notizen": output_json.get("design_notizen", ""),
                                "ki_signal_check": output_json.get("ki_signal_check", {}),
                                "potenzielle_schwaechen": output_json.get("potenzielle_schwaechen", []),
                                "output_hash": output_hash,
                            },
                            ensure_ascii=False,
                        ),
                    },
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

        logger.info(
            "p12 run_id=%s: content_piece inserted id=%s tenant=%s",
            run_id,
            content_piece_id,
            tenant_id,
        )

        # ------------------------------------------------------------------
        # Actual-Cost aufzeichnen
        # ------------------------------------------------------------------
        try:
            asyncio.run(_record_actual_cost(tenant_id, actual_cost))
        except Exception as cost_err:
            logger.warning("p12 run_id=%s: actual-cost recording fehlgeschlagen: %s", run_id, cost_err)

        # ------------------------------------------------------------------
        # 12. Audit-Update: setup_pipeline_run → 'done'
        # ------------------------------------------------------------------
        duration_ms = int((time.monotonic() - t_start) * 1000)
        with sync_session_factory() as session:
            try:
                session.execute(
                    text(
                        "UPDATE setup_pipeline_run SET "
                        "status = 'done', "
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
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cost_usd": str(actual_cost),
                        "duration_ms": duration_ms,
                        "output_hash": output_hash,
                        "prompt_version_hash": prompt_version_hash,
                    },
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

        logger.info(
            "p12 run_id=%s: done in %dms, cost=%.6f USD, output_hash=%s",
            run_id,
            duration_ms,
            actual_cost,
            output_hash[:16],
        )

        # ------------------------------------------------------------------
        # 13. Return
        # ------------------------------------------------------------------
        return {
            "run_id": run_id,
            "status": "done",
            "p12_run_id": run_id,
            "output": output_json,
        }

    except Exception as exc:
        duration_ms = int((time.monotonic() - t_start) * 1000)
        logger.error("p12 run_id=%s tenant=%s: FAILED — %s", run_id, tenant_id, exc, exc_info=True)

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
            logger.error("p12 run_id=%s: Fehler beim Audit-Update auf 'failed': %s", run_id, audit_exc)

        raise self.retry(exc=exc, countdown=30)
