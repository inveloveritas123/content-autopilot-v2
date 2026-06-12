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

"""
Umgestellt: 2026-06-11 (P5-anthropic-provider.md)
  - anthropic-SDK-Bypass entfernt (ANTHROPIC_MODEL_ID / ANTHROPIC_PRICING_KEY entfernt)
  - BACKTEST_MODEL_OVERRIDE ersetzt durch MODEL_TIER_P12 Env-Variable
  - Modell-ID kommt jetzt aus PipelineLLMResult.model_id (Tier S6)
  - Kosten-Schätzung über estimate_tier_cost statt estimate_anthropic_cost
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

from models.base import sync_session_factory
from services.llm_json import parse_json_from_text as _parse_json_from_text
from services.pipeline_llm import (
    call_pipeline_llm,
    estimate_tier_cost,
    resolve_tier,
)
from services.prompt_loader import get_default_prompt_loader
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "schemas", "p12_output_schema.json")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def _load_schema() -> dict:
    with open(os.path.normpath(_SCHEMA_PATH), encoding="utf-8") as f:
        return json.load(f)


_P12_SCHEMA = _load_schema()


# ---------------------------------------------------------------------------
# Pruning-Konstanten — zentral + kanonisch-korrekt (Wortschatz-Bugfix 2026-06-12)
# ---------------------------------------------------------------------------

from tasks.p12_pruning import (
    AVATAR_KEYS_FOR_P12,
    CONTEXT_KEYS_FOR_P12,
    VALUES_KEYS_FOR_P12,  # noqa: F401 — importiert für Vollständigkeit / Tests
    VOICE_KEYS_FOR_P12,
)
from tasks.p12_pruning import (
    prune as _prune_keys,
    prune_values as _prune_values,
)

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _load_active_profiles(tenant_id: str) -> tuple[dict, dict, dict, dict]:
    """Lädt die aktiven Profile aus den 4 Setup-Tabellen über die Lese-Fassade.

    Nutzt services.canonical_profiles (deterministische Aktiv-Row-Auflösung,
    behebt den Multi-Active-Row-Bug) und gibt jeweils das payload-Dict zurück
    (leeres Dict, wenn kein aktiver Eintrag). Loggt eine Warnung bei Alt-v2-Rows.

    Fail-open für customer_values (#43): Die Tabelle tenant_customer_values
    existiert erst nach Migration 053. Schlägt der Load fehl (Tabelle fehlt,
    kein aktives Profil, Netzwerkfehler), wird customer_values={} gesetzt und
    P12 läuft unverändert mit context/voice/avatar weiter — kein Crash.
    Dadurch ist der Code sicher deploybar VOR der Migration.
    """
    from services.canonical_profiles import load_active_profile, load_active_profiles

    # Bestehende 3 Tabellen — existieren auf Prod, kein Fail-open nötig.
    profiles = load_active_profiles(tenant_id)
    customer_context = profiles["customer_context"]["payload"]
    voice_profile = profiles["voice_profile"]["payload"]
    audience_avatar = profiles["audience_avatar"]["payload"]

    # Fail-open: customer_values (#43) — Tabelle existiert erst nach Migration 053.
    # load_active_profiles() iteriert alle TABLE_MAP-Keys; schlägt die Query für
    # tenant_customer_values fehl (Tabelle fehlt auf Prod vor der Migration),
    # fängt dieser Block den Fehler ab und setzt customer_values = {} damit
    # P12 unverändert weiterläuft.
    try:
        values_payload, values_canonical = load_active_profile("customer_values", tenant_id)
        customer_values = values_payload or {}
        if customer_values and not values_canonical:
            logger.warning(
                "p12 tenant=%s: aktives customer_values ist NICHT kanonisch (Alt-Row) "
                "→ Re-Run empfohlen",
                tenant_id,
            )
    except Exception as exc:
        logger.warning(
            "p12 tenant=%s: customer_values-Load fehlgeschlagen (%s: %s) "
            "— fail-open, weiter ohne Werte-Profil",
            tenant_id,
            type(exc).__name__,
            exc,
        )
        customer_values = {}

    for ptype, info in profiles.items():
        if info["payload"] and not info["is_canonical"]:
            logger.warning(
                "p12 tenant=%s: aktives %s ist NICHT kanonisch (Alt-v2-Row) "
                "→ Re-Run von P0x empfohlen, Voice-Qualität eingeschränkt",
                tenant_id,
                ptype,
            )

    logger.debug(
        "p12 _load_active_profiles tenant=%s: "
        "customer_context=%d keys, voice_profile=%d keys, "
        "audience_avatar=%d keys, customer_values=%d keys",
        tenant_id,
        len(customer_context),
        len(voice_profile),
        len(audience_avatar),
        len(customer_values),
    )
    return customer_context, voice_profile, audience_avatar, customer_values


def _prune_for_p12(
    customer_context: dict,
    voice_profile: dict,
    audience_avatar: dict,
    customer_values: dict,
) -> tuple[dict, dict, dict, dict]:
    """Reduziert die Profile auf die für P12 relevanten Felder.

    Nur vorhandene Keys werden übernommen — kein KeyError bei fehlenden Feldern.
    customer_values wird über prune_values() verarbeitet (Status-Filter +
    quellen/status-Stripping für Token-Hygiene). Leerer Payload → {} (fail-open).
    """
    pruned_context = _prune_keys(customer_context, CONTEXT_KEYS_FOR_P12)
    pruned_voice = _prune_keys(voice_profile, VOICE_KEYS_FOR_P12)
    pruned_avatar = _prune_keys(audience_avatar, AVATAR_KEYS_FOR_P12)
    pruned_values = _prune_values(customer_values)
    return pruned_context, pruned_voice, pruned_avatar, pruned_values


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
    from services.kill_switch import KillSwitchTriggered, check_kill_switch

    try:
        check_kill_switch(tenant_id)
    except KillSwitchTriggered:
        return {"status": "aborted", "reason": "tenant_disabled"}
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
                # model_id wird beim Audit-Update mit dem echten Router-Wert überschrieben
                {"id": run_id, "tenant_id": tenant_id, "model_id": "pending"},
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("p12 run_id=%s: failed to create setup_pipeline_run: %s", run_id, exc)
            raise

    logger.info(
        "p12 run_id=%s tenant=%s idea_id=%s: pipeline run created", run_id, tenant_id, idea_id
    )

    t_start = time.monotonic()

    try:
        # ------------------------------------------------------------------
        # 2. Cost-Cap prüfen
        # ------------------------------------------------------------------
        from services.cost_cap import CostCapExceeded
        from services.llm import BudgetExceededError

        _tier, _ = resolve_tier("P12")
        estimated_cost = estimate_tier_cost(_tier, 3000, 1500)
        logger.info("p12 run_id=%s: estimated cost=%.6f USD", run_id, estimated_cost)

        try:
            asyncio.run(_run_cost_check(tenant_id, estimated_cost))
        except (CostCapExceeded, BudgetExceededError):
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
        customer_context, voice_profile, audience_avatar, customer_values = (
            _load_active_profiles(tenant_id)
        )

        # ------------------------------------------------------------------
        # 4. Profile prunen
        # ------------------------------------------------------------------
        pruned_context, pruned_voice, pruned_avatar, pruned_values = _prune_for_p12(
            customer_context, voice_profile, audience_avatar, customer_values
        )
        logger.debug(
            "p12 run_id=%s: pruned keys — context=%d voice=%d avatar=%d values=%d",
            run_id,
            len(pruned_context),
            len(pruned_voice),
            len(pruned_avatar),
            len(pruned_values),
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
        # Phase 7.4: Top-5 Hooks aus library als Inspiration (Allow-List, kein Forced-Use)
        hook_inspirations: list[dict] = []
        try:
            with sync_session_factory() as _hook_db:
                _hook_rows = _hook_db.execute(
                    text(
                        "SELECT id, hook_text, hook_type, performance_score "
                        "FROM hook_library "
                        "WHERE tenant_id = :tid "
                        "ORDER BY performance_score DESC, used_count DESC, created_at DESC "
                        "LIMIT 5"
                    ),
                    {"tid": tenant_id},
                ).fetchall()
                for hr in _hook_rows:
                    hook_inspirations.append(
                        {
                            "id": str(hr.id),
                            "hook_text": hr.hook_text,
                            "type": hr.hook_type,
                            "performance": float(hr.performance_score or 0),
                        }
                    )
        except Exception:
            pass  # Fail-safe: ohne Hook-Library generieren

        context_payload = {
            "customer_context": pruned_context,
            "voice_profile": pruned_voice,
            "audience_avatar": pruned_avatar,
            "answers": answers,
            "idea_id": idea_id,
        }
        # #43 Schritt 3: Werte-Entität in den Prompt-Kontext injizieren.
        # Fail-open: pruned_values ist {} wenn Tabelle noch nicht existiert
        # (vor Migration 053) oder kein aktives Profil → P12 läuft unverändert.
        if pruned_values:
            context_payload["customer_values"] = pruned_values
        if hook_inspirations:
            context_payload["hook_inspirations"] = hook_inspirations
        context_json_str = json.dumps(context_payload, ensure_ascii=False)
        user_prompt = loaded.user_prompt_template.replace("{context_json}", context_json_str)

        # ------------------------------------------------------------------
        # 7. LLM-Call über den Seam (kein direkter SDK-Aufruf)
        # BACKTEST_MODEL_OVERRIDE wird durch MODEL_TIER_P12 Env-Variable ersetzt
        # ------------------------------------------------------------------
        res = call_pipeline_llm(
            prompt_key="P12",
            system_prompt=loaded.system_prompt,
            user_content=user_prompt,
            tenant_id=tenant_id,
            max_tokens=3000,
        )

        raw_text = res.text
        model_id = res.model_id
        logger.debug("p12 run_id=%s: LLM-Antwort erhalten (%d Zeichen)", run_id, len(raw_text))

        # ------------------------------------------------------------------
        # 8. Token-Usage tracken (cache_read NICHT zu input_tokens addieren)
        # ------------------------------------------------------------------
        input_tokens = res.input_tokens
        output_tokens = res.output_tokens
        cache_read = res.cache_read_tokens
        logger.info(
            "p12 run_id=%s: usage input=%d output=%d cache_read=%d tenant=%s",
            run_id,
            input_tokens,
            output_tokens,
            cache_read,
            tenant_id,
        )

        actual_cost = res.cost_usd

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
        output_hash = hashlib.sha256(json.dumps(output_json, sort_keys=True).encode()).hexdigest()

        # #145 Phase 4.1: Kategorie aus LLM-Output validieren (NULL bei Drift)
        _ALLOWED_CATEGORIES = {"news", "persoenlich", "trust", "praxis"}
        _raw_cat = (output_json.get("kategorie") or "").strip().lower()
        category = _raw_cat if _raw_cat in _ALLOWED_CATEGORIES else None
        if _raw_cat and category is None:
            logger.warning(
                "p12 run_id=%s: ungültige LLM-Kategorie '%s' — auf NULL gesetzt", run_id, _raw_cat
            )

        content_piece_id = str(uuid.uuid4())
        with sync_session_factory() as session:
            try:
                session.execute(
                    text(
                        "INSERT INTO content_pieces "
                        "(id, tenant_id, idea_id, channel, content_text, content_metadata, status, category, created_at) "
                        "VALUES (:id, :tenant_id, :idea_id, 'linkedin', :content_text, "
                        "CAST(:content_metadata AS jsonb), 'draft', :category, now())"
                    ),
                    {
                        "id": content_piece_id,
                        "tenant_id": tenant_id,
                        "idea_id": idea_id,
                        "content_text": post_text,
                        "category": category,
                        "content_metadata": json.dumps(
                            {
                                "p12_run_id": run_id,
                                "alternative_opener": output_json.get("alternative_opener", []),
                                "design_notizen": output_json.get("design_notizen", ""),
                                "ki_signal_check": output_json.get("ki_signal_check", {}),
                                "potenzielle_schwaechen": output_json.get(
                                    "potenzielle_schwaechen", []
                                ),
                                "kategorie_raw": _raw_cat,
                                "inspired_by_hook_id": output_json.get("inspired_by_hook_id"),
                                "output_hash": output_hash,
                            },
                            ensure_ascii=False,
                        ),
                    },
                )
                # Phase 7.4: track_use wenn LLM einen Library-Hook als Inspiration nennt
                _inspired_id = output_json.get("inspired_by_hook_id")
                if _inspired_id:
                    try:
                        session.execute(
                            text(
                                "UPDATE hook_library SET used_count = used_count + 1, "
                                "  last_used_at = now() "
                                "WHERE id = CAST(:hid AS uuid) AND tenant_id = :tid"
                            ),
                            {"hid": str(_inspired_id), "tid": tenant_id},
                        )
                    except Exception:
                        pass  # Drift-safe: ungültige hook_id wird einfach ignoriert
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
            logger.warning(
                "p12 run_id=%s: actual-cost recording fehlgeschlagen: %s", run_id, cost_err
            )

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
                        "model_id = :model_id, "
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
                        "model_id": model_id,
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

    except BudgetExceededError:
        # BUG-1-Fix: Router-Budget überschritten (HTTP 412) → paused_for_cost, kein Retry
        duration_ms = int((time.monotonic() - t_start) * 1000)
        logger.warning(
            "p12 run_id=%s tenant=%s: Router-Budget überschritten (412), pausing", run_id, tenant_id
        )
        try:
            with sync_session_factory() as session:
                session.execute(
                    text(
                        "UPDATE setup_pipeline_run SET "
                        "status = 'paused_for_cost', "
                        "finished_at = now() "
                        "WHERE id = :run_id"
                    ),
                    {"run_id": run_id},
                )
                session.commit()
        except Exception as audit_exc:
            logger.error(
                "p12 run_id=%s: audit update (paused_for_cost) fehlgeschlagen: %s",
                run_id,
                audit_exc,
            )
        return {"run_id": run_id, "status": "paused_for_cost"}

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
            logger.error(
                "p12 run_id=%s: Fehler beim Audit-Update auf 'failed': %s", run_id, audit_exc
            )

        raise self.retry(exc=exc, countdown=30)
