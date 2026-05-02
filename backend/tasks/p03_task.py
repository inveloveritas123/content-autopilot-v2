"""
P03 Voice-Profile Task — extrahiert das Stimmprofil eines Tenants aus
Transkripten und optionalen Beispieltexten.

Workflow:
1. Setup-Pipeline-Run erstellen (stage='p03', status='running')
2. Cost-Cap-Schätzung berechnen
3. Prompt aus Nextcloud laden (PromptLoader, gecacht)
4. Anthropic-Call mit Prompt-Caching (cache_control ephemeral)
5. JSON-Output parsen + Schema validieren
6. In tenant_voice_profile inserieren (is_active=False, neue Version)
7. Audit-Update (tokens, cost, duration, output_hash)

Bypass-Pfad: Wenn bypass_with_existing_json=True + existing_json vorhanden →
Schema validieren und direkt inserieren mit source='md_upload'.
"""
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

# Schema laden — einmalig beim Modulimport
_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "schemas", "p03_output_schema.json")

def _load_schema() -> dict:
    with open(os.path.normpath(_SCHEMA_PATH), "r", encoding="utf-8") as f:
        return json.load(f)

_P03_SCHEMA = _load_schema()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _parse_json_from_text(raw: str) -> dict:
    """Extrahiert JSON aus dem LLM-Output.

    Versucht zuerst direktes Parsen, danach Extraktion aus einem ```json-Block.
    """
    raw = raw.strip()
    # Direkter Parse-Versuch
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fenced code block: ```json ... ```
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


def _validate_schema(data: dict) -> None:
    """Validiert das geparste JSON gegen das P03-Output-Schema."""
    jsonschema.validate(instance=data, schema=_P03_SCHEMA)


def _insert_voice_profile(
    session,
    tenant_id: str,
    payload: dict,
    source: str,
    prompt_version_hash: str,
    model_id: str,
) -> str:
    """Inseriert einen neuen voice_profile-Eintrag und gibt die neue ID zurück."""
    # Nächste Versionsnummer ermitteln
    row = session.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
            "FROM tenant_voice_profile WHERE tenant_id = :tenant_id"
        ),
        {"tenant_id": tenant_id},
    ).fetchone()
    next_version = row.next_version if row else 1

    new_id = str(uuid.uuid4())
    session.execute(
        text(
            "INSERT INTO tenant_voice_profile "
            "(id, tenant_id, version, is_active, source, payload, prompt_version_hash, model_id) "
            "VALUES (:id, :tenant_id, :version, false, :source, :payload::jsonb, "
            ":prompt_version_hash, :model_id)"
        ),
        {
            "id": new_id,
            "tenant_id": tenant_id,
            "version": next_version,
            "source": source,
            "payload": json.dumps(payload),
            "prompt_version_hash": prompt_version_hash,
            "model_id": model_id,
        },
    )
    return new_id


# ---------------------------------------------------------------------------
# Celery Task
# ---------------------------------------------------------------------------

@celery_app.task(name="tasks.p03_task.run_p03", bind=True, max_retries=2)
def run_p03(
    self,
    tenant_id: str,
    transcript: str,
    written_texts: list = None,
    bypass_with_existing_json: bool = False,
    existing_json: dict = None,
) -> dict:
    """P03 Voice-Profile Extraktion.

    Args:
        tenant_id: Tenant-Identifier.
        transcript: Transkript-Text (Interview / Podcast / etc.).
        written_texts: Optionale Beispieltexte des Unternehmers.
        bypass_with_existing_json: Wenn True wird kein LLM aufgerufen.
        existing_json: Fertiges JSON (z.B. aus MD-Upload), nur bei bypass.

    Returns:
        dict mit run_id, status und optionalem voice_profile_id.
    """
    run_id = str(uuid.uuid4())

    # ── Bypass-Pfad ────────────────────────────────────────────────────────────
    if bypass_with_existing_json and existing_json:
        try:
            _validate_schema(existing_json)
        except jsonschema.ValidationError as exc:
            logger.error("P03 bypass schema validation failed: %s", exc.message)
            raise

        with sync_session_factory() as session:
            try:
                _insert_voice_profile(
                    session=session,
                    tenant_id=tenant_id,
                    payload=existing_json,
                    source="md_upload",
                    prompt_version_hash="bypass",
                    model_id="bypass",
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

        logger.info("P03 bypass done for tenant=%s run_id=%s", tenant_id, run_id)
        return {"run_id": run_id, "status": "done", "bypass": True}

    # ── Normaler Pfad ──────────────────────────────────────────────────────────

    # 1. Setup-Pipeline-Run erstellen
    with sync_session_factory() as session:
        try:
            session.execute(
                text(
                    "INSERT INTO setup_pipeline_run "
                    "(id, tenant_id, stage, model_id, status) "
                    "VALUES (:id, :tenant_id, 'p03', :model_id, 'running')"
                ),
                {"id": run_id, "tenant_id": tenant_id, "model_id": ANTHROPIC_MODEL_ID},
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("P03 failed to create setup_pipeline_run: %s", exc)
            raise

    t_start = time.monotonic()

    try:
        # 2. Cost-Cap-Schätzung (sync — reine Rechenoperation)
        from services.cost_cap import estimate_anthropic_cost
        est = estimate_anthropic_cost(ANTHROPIC_MODEL_ID, 3000, 1500)
        logger.info("P03 estimated cost=%.6f USD for tenant=%s", est, tenant_id)

        # 3. Prompt laden
        loader = get_default_prompt_loader()
        loaded = loader.load("P03")
        prompt_version_hash = loaded.sha

        # 4. Anthropic-Call mit cache_control
        from config import settings
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        user_content = loaded.user_prompt_template + f"\n\n<transkript>{transcript}</transkript>"
        if written_texts:
            for i, txt in enumerate(written_texts, 1):
                user_content += f"\n<beispieltext_{i}>{txt}</beispieltext_{i}>"

        response = client.messages.create(
            model=ANTHROPIC_MODEL_ID,
            max_tokens=2000,
            system=[
                {
                    "type": "text",
                    "text": loaded.system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
        )

        raw_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0)
        logger.info(
            "P03 usage: input=%d output=%d cache_read=%d tenant=%s",
            input_tokens,
            output_tokens,
            cache_read,
            tenant_id,
        )

        # 5. JSON-Parsing + Schema-Validierung
        parsed = _parse_json_from_text(raw_text)
        _validate_schema(parsed)

        # 6. DB-Insert in tenant_voice_profile
        actual_cost = estimate_anthropic_cost(ANTHROPIC_MODEL_ID, input_tokens, output_tokens)
        output_hash = hashlib.sha256(json.dumps(parsed, sort_keys=True).encode()).hexdigest()
        duration_ms = int((time.monotonic() - t_start) * 1000)

        voice_profile_id = None
        with sync_session_factory() as session:
            try:
                voice_profile_id = _insert_voice_profile(
                    session=session,
                    tenant_id=tenant_id,
                    payload=parsed,
                    source="transcript",
                    prompt_version_hash=prompt_version_hash,
                    model_id=ANTHROPIC_MODEL_ID,
                )
                # 7. Audit-Update
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
            "P03 done tenant=%s run_id=%s voice_profile_id=%s cost=%.6f USD duration=%dms",
            tenant_id,
            run_id,
            voice_profile_id,
            actual_cost,
            duration_ms,
        )

        return {
            "run_id": run_id,
            "status": "done",
            "voice_profile_id": voice_profile_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": actual_cost,
            "duration_ms": duration_ms,
        }

    except Exception as exc:
        duration_ms = int((time.monotonic() - t_start) * 1000)
        logger.error("P03 failed tenant=%s run_id=%s: %s", tenant_id, run_id, exc, exc_info=True)

        # Audit-Update auf failed
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
            logger.error("P03 audit update failed: %s", audit_exc)

        raise self.retry(exc=exc, countdown=30)
