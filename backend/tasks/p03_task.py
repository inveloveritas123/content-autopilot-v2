"""
P03 Voice-Profile Task — extrahiert das Stimmprofil eines Tenants aus
Transkripten und optionalen Beispieltexten.

Workflow:
1. Setup-Pipeline-Run erstellen (stage='p03', status='running')
2. Cost-Cap-Schätzung berechnen
3. Prompt aus Nextcloud laden (PromptLoader, gecacht)
4. LLM-Call über call_pipeline_llm (Seam → Router, kein direkter SDK-Aufruf)
5. JSON-Output parsen + Schema validieren
6. In tenant_voice_profile inserieren (is_active=False, neue Version)
7. Audit-Update (tokens, cost, duration, output_hash)

Bypass-Pfad: Wenn bypass_with_existing_json=True + existing_json vorhanden →
Schema validieren und direkt inserieren mit source='md_upload'.

Umgestellt: 2026-06-11 (P5-anthropic-provider.md)
  - anthropic-SDK-Bypass entfernt (ANTHROPIC_MODEL_ID entfernt)
  - Modell-ID kommt jetzt aus PipelineLLMResult.model_id
  - Kosten-Schätzung über estimate_tier_cost statt estimate_anthropic_cost
"""

import hashlib
import json
import logging
import re
import time
import uuid

from sqlalchemy import text

from models.base import sync_session_factory
from services.llm_json import parse_json_from_text as _parse_json_from_text
from services.pipeline_llm import (
    call_pipeline_llm,
    estimate_tier_cost,
    resolve_tier,
)
from services.prompt_loader import get_default_prompt_loader
from services.schema_transformer import build_canonical_meta, finalize_canonical
from tasks.canonical_wiring import fetch_tenant_meta, now_iso
from tasks.celery_app import celery_app
from tasks.p03_voice_fallback import run_p03_voice_fallback

logger = logging.getLogger(__name__)


def _insert_voice_profile(
    session,
    tenant_id: str,
    payload: dict,
    source: str,
    prompt_version_hash: str,
    model_id: str,
    project_id: str | None = None,
) -> str:
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
            "(id, tenant_id, version, is_active, source, payload, prompt_version_hash, model_id, project_id) "
            "VALUES (:id, :tenant_id, :version, false, :source, CAST(:payload AS jsonb), "
            ":prompt_version_hash, :model_id, :project_id)"
        ),
        {
            "id": new_id,
            "tenant_id": tenant_id,
            "version": next_version,
            "source": source,
            "payload": json.dumps(payload),
            "prompt_version_hash": prompt_version_hash,
            "model_id": model_id,
            "project_id": project_id,
        },
    )
    return new_id


# ---------------------------------------------------------------------------
# LinkedIn-Post-Filter (Issue #89)
# ---------------------------------------------------------------------------

_MAX_POSTS = 20
_MAX_CHARS_PER_POST = 3000

# Injection-Schutz: Patterns die auf Prompt-Injection hindeuten
_INJECTION_PATTERNS = [
    re.compile(
        r"\b(ignore (all )?previous instructions?|vergiss (alle )?anweisungen)\b", re.IGNORECASE
    ),
    re.compile(r"\b(system prompt|system-prompt|<\|im_start\|>|<\|im_end\|>)\b", re.IGNORECASE),
    re.compile(r"(##+ System|##+ Assistant|##+ User)\b", re.IGNORECASE),
    re.compile(r"<(script|iframe|object|embed)[^>]*>", re.IGNORECASE),
    re.compile(r"\{\{.*?\}\}", re.DOTALL),  # template injection
]


def _filter_linkedin_posts(posts: list) -> list:
    """Filter und sanitize LinkedIn-Posts für P03-Input.

    - Längen-Limit: max 3000 Zeichen pro Post
    - Anzahl-Limit: max 20 Posts
    - Injection-Schutz: Posts mit verdächtigen Patterns werden verworfen
    - Entfernt XML-Tags und normalisiert Whitespace
    """
    clean: list = []
    for raw in posts or []:
        if not isinstance(raw, str):
            continue
        post = raw.strip()
        if not post:
            continue

        # Injection check: verwerfe den Post wenn Muster gefunden
        if any(p.search(post) for p in _INJECTION_PATTERNS):
            logger.warning(
                "[P03] LinkedIn-Post mit Injection-Muster verworfen (Länge=%d)", len(post)
            )
            continue

        # Längen-Limit
        if len(post) > _MAX_CHARS_PER_POST:
            post = post[:_MAX_CHARS_PER_POST] + "…"

        # Entferne XML-Tags (verhindert Prompt-Injection via <transkript> etc.)
        post = re.sub(r"<[^>]+>", "", post)

        # Normalisiere Whitespace
        post = re.sub(r"\n{3,}", "\n\n", post).strip()

        if post:
            clean.append(post)

        if len(clean) >= _MAX_POSTS:
            break

    return clean


# ---------------------------------------------------------------------------
# Celery Task
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.p03_task.run_p03", bind=True, max_retries=2)
def run_p03(
    self,
    tenant_id: str,
    transcript: str,
    written_texts: list | None = None,
    linkedin_posts: list | None = None,
    bypass_with_existing_json: bool = False,
    existing_json: dict | None = None,
    project_id: str | None = None,
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
    from services.kill_switch import KillSwitchTriggered, check_kill_switch

    try:
        check_kill_switch(tenant_id)
    except KillSwitchTriggered:
        return {"status": "aborted", "reason": "tenant_disabled"}
    run_id = str(uuid.uuid4())

    # ── Bypass-Pfad ────────────────────────────────────────────────────────────
    if bypass_with_existing_json and existing_json:
        # Kanonisch absichern statt hartem v2-ValidationError: _meta server-seitig,
        # Schema-Verstoesse als _meta.luecken dokumentieren (kein Hard-Fail).
        tenant_name, agentur_id = fetch_tenant_meta(tenant_id)
        llm_meta = (
            existing_json.get("_meta") if isinstance(existing_json.get("_meta"), dict) else None
        )
        canonical_meta = build_canonical_meta(
            "p03",
            tenant_id=tenant_id,
            model="bypass",
            generated_at=now_iso(),
            tenant_name=tenant_name,
            agentur_id=agentur_id,
            llm_meta=llm_meta,
        )
        bypass_payload, schema_errors = finalize_canonical(
            "p03", existing_json, meta=canonical_meta
        )
        if schema_errors:
            logger.warning(
                "P03 bypass tenant=%s: %d kanonische Schema-Luecke(n) in _meta.luecken dokumentiert",
                tenant_id,
                len(schema_errors),
            )

        with sync_session_factory() as session:
            try:
                _insert_voice_profile(
                    session=session,
                    tenant_id=tenant_id,
                    payload=bypass_payload,
                    source="md_upload",
                    prompt_version_hash="bypass",
                    model_id="bypass",
                    project_id=project_id,
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
                    "(id, tenant_id, stage, status) "
                    "VALUES (:id, :tenant_id, 'p03', 'running')"
                ),
                {"id": run_id, "tenant_id": tenant_id},
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("P03 failed to create setup_pipeline_run: %s", exc)
            raise

    t_start = time.monotonic()

    try:
        # 2. Cost-Cap-Schätzung + Enforcement
        from services.cost_cap import CostCapExceeded
        from services.llm import BudgetExceededError

        _tier, _ = resolve_tier("P03")
        est = estimate_tier_cost(_tier, 3000, 1500)
        logger.info("P03 estimated cost=%.6f USD for tenant=%s", est, tenant_id)
        try:
            import asyncio as _asyncio

            from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
            from sqlalchemy.orm import sessionmaker as _sm

            from config import settings as _s
            from services.cost_cap import CostCapMiddleware
            from services.rls import tenant_session

            async def _p03_cap_check():
                _engine = create_async_engine(_s.database_url, pool_pre_ping=True)
                _Session = _sm(_engine, class_=AsyncSession, expire_on_commit=False)
                try:
                    async with tenant_session(_Session, tenant_id) as _sess:
                        await CostCapMiddleware(_sess).check_and_record(tenant_id, est)
                finally:
                    await _engine.dispose()

            _asyncio.run(_p03_cap_check())
        except (CostCapExceeded, BudgetExceededError):
            logger.warning(
                "P03 run_id=%s tenant=%s: daily cost cap exceeded, pausing", run_id, tenant_id
            )
            with sync_session_factory() as session:
                session.execute(
                    text(
                        "UPDATE setup_pipeline_run SET status='paused_for_cost', finished_at=now() WHERE id=:id"
                    ),
                    {"id": run_id},
                )
                session.commit()
            return {"run_id": run_id, "status": "paused_for_cost"}
        except Exception as cap_err:
            logger.warning("P03 cost-cap check failed (fail-open): %s", cap_err)

        # 2b. Voice-Fallback (Issue #40): wenn keine Voice-Quelle vorhanden,
        #     plausiblen Ton aus Kontext+Avatar ableiten und kanonisch schreiben.
        #     Bei Erfolg → frühzeitiger Return (Fallback-Profil geschrieben).
        #     Bei Fehler oder vorhandener Voice-Quelle → regulärer Pfad unverändert.
        tenant_name_for_fallback, agentur_id_for_fallback = fetch_tenant_meta(tenant_id)
        fallback_result = run_p03_voice_fallback(
            tenant_id=tenant_id,
            transcript=transcript,
            written_texts=written_texts,
            linkedin_posts=linkedin_posts,
            tenant_name=tenant_name_for_fallback,
            agentur_id=agentur_id_for_fallback,
            project_id=project_id,
        )
        if fallback_result is not None:
            # Fallback erfolgreich → kanonisches Voice-Profil mit Provenance geschrieben.
            # Audit-Update: Fallback-Run als done markieren (kein output_hash, da kein regulärer LLM-Call).
            duration_ms = int((time.monotonic() - t_start) * 1000)
            try:
                with sync_session_factory() as session:
                    session.execute(
                        text(
                            "UPDATE setup_pipeline_run SET "
                            "status = 'done', "
                            "input_tokens = :input_tokens, "
                            "output_tokens = :output_tokens, "
                            "cost_usd = :cost_usd, "
                            "duration_ms = :duration_ms, "
                            "prompt_version_hash = 'voice_fallback', "
                            "finished_at = now() "
                            "WHERE id = :run_id"
                        ),
                        {
                            "run_id": run_id,
                            "input_tokens": fallback_result.get("input_tokens", 0),
                            "output_tokens": fallback_result.get("output_tokens", 0),
                            "cost_usd": str(fallback_result.get("cost_usd", 0.0)),
                            "duration_ms": duration_ms,
                        },
                    )
                    session.commit()
            except Exception as audit_exc:
                logger.warning("P03 fallback audit-update fehlgeschlagen: %s", audit_exc)

            logger.info(
                "P03 voice_fallback done tenant=%s run_id=%s duration=%dms",
                tenant_id,
                run_id,
                duration_ms,
            )
            return {
                "run_id": run_id,
                "status": "done",
                "voice_fallback": True,
                "source": "voice_fallback",
                "input_tokens": fallback_result.get("input_tokens", 0),
                "output_tokens": fallback_result.get("output_tokens", 0),
                "cost_usd": fallback_result.get("cost_usd", 0.0),
                "duration_ms": duration_ms,
            }

        # 3. Prompt laden
        loader = get_default_prompt_loader()
        loaded = loader.load("P03")
        prompt_version_hash = loaded.sha

        # 4. User-Content zusammenbauen
        user_content = loaded.user_prompt_template + f"\n\n<transkript>{transcript}</transkript>"
        if written_texts:
            for i, txt in enumerate(written_texts, 1):
                user_content += f"\n<beispieltext_{i}>{txt}</beispieltext_{i}>"

        filtered_posts = _filter_linkedin_posts(linkedin_posts) if linkedin_posts else []
        if filtered_posts:
            user_content += "\n\n<linkedin_history>\n"
            for i, post in enumerate(filtered_posts, 1):
                user_content += f"--- Post {i} ---\n{post}\n\n"
            user_content += "</linkedin_history>"
            logger.info(
                "P03 run_id=%s: %d LinkedIn-Posts als Voice-Quelle hinzugefügt",
                run_id,
                len(filtered_posts),
            )

        # 5. LLM-Call über den Seam (kein direkter SDK-Aufruf)
        res = call_pipeline_llm(
            prompt_key="P03",
            system_prompt=loaded.system_prompt,
            user_content=user_content,
            tenant_id=tenant_id,
        )

        raw_text = res.text
        input_tokens = res.input_tokens
        output_tokens = res.output_tokens
        actual_cost = res.cost_usd
        model_id = res.model_id
        logger.info(
            "P03 usage: input=%d output=%d cache_read=%d tenant=%s",
            input_tokens,
            output_tokens,
            res.cache_read_tokens,
            tenant_id,
        )

        # 6. JSON-Parsing + kanonische Validierung (Soft-Fail mit _meta.luecken)
        try:
            parsed = _parse_json_from_text(raw_text)
        except ValueError:
            logger.warning(
                "P03 run_id=%s: JSON-Parse fehlgeschlagen, 1 Korrektur-Call",
                run_id,
            )
            retry_res = call_pipeline_llm(
                prompt_key="P03",
                system_prompt=loaded.system_prompt,
                user_content=(
                    user_content
                    + "\n\n---\n\nDeine vorherige Antwort war kein reines JSON-Objekt. "
                    "Antworte ausschließlich mit dem JSON-Objekt. "
                    "Kein Text davor, kein Text danach, keine ```json-Backticks."
                ),
                tenant_id=tenant_id,
            )
            raw_text = retry_res.text
            input_tokens += retry_res.input_tokens
            output_tokens += retry_res.output_tokens
            actual_cost += retry_res.cost_usd
            parsed = _parse_json_from_text(raw_text)

        tenant_name, agentur_id = fetch_tenant_meta(tenant_id)
        llm_meta = parsed.get("_meta") if isinstance(parsed.get("_meta"), dict) else None
        canonical_meta = build_canonical_meta(
            "p03",
            tenant_id=tenant_id,
            model=model_id,
            generated_at=now_iso(),
            tenant_name=tenant_name,
            agentur_id=agentur_id,
            token_usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
            llm_meta=llm_meta,
        )
        parsed, schema_errors = finalize_canonical("p03", parsed, meta=canonical_meta)
        if schema_errors:
            logger.warning(
                "P03 run_id=%s: %d kanonische Schema-Luecke(n) in _meta.luecken dokumentiert",
                run_id,
                len(schema_errors),
            )

        # 7. DB-Insert in tenant_voice_profile (kanonischer Payload inkl. _meta)
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
                    model_id=model_id,
                    project_id=project_id,
                )
                # Audit-Update
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

    except BudgetExceededError:
        # BUG-1-Fix: Router-Budget überschritten (HTTP 412) → paused_for_cost, kein Retry
        duration_ms = int((time.monotonic() - t_start) * 1000)
        logger.warning(
            "P03 run_id=%s tenant=%s: Router-Budget überschritten (412), pausing", run_id, tenant_id
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
            logger.error("P03 audit update (paused_for_cost) failed: %s", audit_exc)
        return {"run_id": run_id, "status": "paused_for_cost"}

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
