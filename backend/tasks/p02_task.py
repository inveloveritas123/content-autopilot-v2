"""
P02-Service — Website-Analyse für den Tenant.

Workflow (additiv, fail-open):
1. Guard: kein website_url → skip (kein Fehler)
2. Kill-Switch prüfen (wie P01/P03/P04)
3. Cost-Cap-Vorcheck (fail-open: Netzfehler bei Cap-Check → weiter)
4. Website fetchen via httpx, Text auf 8000 Zeichen kappen
5. Netzfehler / Timeout → skip (fail-open, kein Crash)
6. LLM-Call via call_pipeline_llm (Seam, Prompt-Key='P02')
7. Ergebnis additiv in tenants.settings['p02_website_context'] speichern
   (existierender JSONB-Key, kein Schema-Change, tenant-gescopt, E3-konform)
8. NICHT in setup_pipeline_task.py eingehängt — separater Task-Aufruf

Additiv-Prinzip:
  - Schreibt einen einzelnen Key in tenants.settings JSONB (jsonb_set).
  - Berührt keine andere Tabelle, kein bestehender Eintrag wird überschrieben
    (nur p02_website_context).
  - Kein Eintrag in setup_pipeline_run (Audit-Log wäre invasiv; P02 ist optional).

Platzhalter-Prompt:
  _P02_PLACEHOLDER_SYSTEM_PROMPT — aktiv bis Chris/Louis den echten P02-Prompt
  unter content-truth/prompts/P02-*.md ablegen.
  CHRIS-BACKLOG: P02-Prompt fehlt, Platzhalter aktiv, Issue #39.

Py3.9-kompatibel: str | None via __future__.annotations, datetime.timezone.utc.
"""

from __future__ import annotations  # Py3.9: str | None Syntax

import datetime
import json
import logging
import uuid

import httpx

from services.pipeline_llm import call_pipeline_llm
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Website-Fetch-Konstanten
# ---------------------------------------------------------------------------

_WEBSITE_FETCH_TIMEOUT = 20  # Sekunden
_WEBSITE_TEXT_MAX_CHARS = 8000  # Kappen vor LLM-Call

# ---------------------------------------------------------------------------
# Platzhalter-System-Prompt
# ---------------------------------------------------------------------------
# TODO Chris/Louis: echten P02-Prompt unter content-truth/prompts/P02-*.md ablegen.
# CHRIS-BACKLOG: P02-Prompt fehlt, Platzhalter aktiv in backend/tasks/p02_task.py:
#   _P02_PLACEHOLDER_SYSTEM_PROMPT, Issue #39.
_P02_PLACEHOLDER_SYSTEM_PROMPT = (
    "Du bist ein Website-Analyst. Analysiere den folgenden Website-Text "
    "und erstelle eine kompakte, strukturierte Zusammenfassung auf Deutsch. "
    "Extrahiere: Unternehmensname, Branche, Kernleistungen (max 5 Stichworte), "
    "Zielgruppe (max 3 Stichworte), USP (max 150 Zeichen), Tonalität (formal/informal/technisch/emotional). "
    "Antworte AUSSCHLIESSLICH mit JSON: "
    '{"unternehmensname": "...", "branche": "...", "kernleistungen": [...], '
    '"zielgruppe": [...], "usp": "...", "tonalitaet": "..."}'
)


def _load_p02_prompt_if_available() -> str:
    """Lädt den P02-Prompt aus content-truth/prompts/ falls vorhanden.

    Gibt den Platzhalter zurück wenn kein P02-*.md existiert.
    Fail-open: Lade-Fehler → Platzhalter (kein Crash).
    """
    try:
        from services.prompt_loader import get_default_prompt_loader

        loader = get_default_prompt_loader()
        loaded = loader.load("P02")
        if loaded and loaded.system_prompt:
            logger.info("p02: echter Prompt aus content-truth geladen (sha=%s)", loaded.sha[:12])
            return loaded.system_prompt
    except Exception as exc:
        logger.debug("p02: kein P02-Prompt in content-truth verfügbar (%s) → Platzhalter", exc)
    return _P02_PLACEHOLDER_SYSTEM_PROMPT


def _fetch_website_text(url: str) -> str | None:
    """Fetcht Website-Text via httpx (synchron).

    Gibt den rohen Text (auf _WEBSITE_TEXT_MAX_CHARS gekürzt) zurück.
    Netzfehler / Timeout → None (fail-open, kein Exception-Raise).
    """
    try:
        headers = {
            "User-Agent": "ContentAutopilot/2.0 (Website-Analyse)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.5",
        }
        with httpx.Client(timeout=_WEBSITE_FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            raw_html = resp.text

        # HTML-Tags entfernen + Whitespace normalisieren
        import re

        text = re.sub(r"<[^>]+>", " ", raw_html)
        text = re.sub(r"\s+", " ", text).strip()

        if not text or len(text) < 50:
            logger.warning("p02: Website %s lieferte zu wenig Text (%d chars)", url, len(text))
            return None

        # Kappen
        if len(text) > _WEBSITE_TEXT_MAX_CHARS:
            text = text[:_WEBSITE_TEXT_MAX_CHARS]

        return text

    except httpx.TimeoutException:
        logger.warning("p02: Timeout beim Fetchen von %s", url)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("p02: HTTP %d beim Fetchen von %s", exc.response.status_code, url)
        return None
    except Exception as exc:
        logger.warning("p02: Fetch-Fehler für %s: %s", url, exc)
        return None


def _save_website_context(tenant_id: str, context: dict) -> None:
    """Speichert p02_website_context additiv in tenants.settings JSONB.

    Verwendet jsonb_set → kein Überschreiben anderer Settings-Keys.
    Tenant-gescopt (E3-konform). Fail-open: DB-Fehler → nur Warning, kein Crash.
    """
    from sqlalchemy import text

    from models.base import sync_session_factory

    generated_at = datetime.datetime.now(datetime.UTC).isoformat()
    payload = {**context, "generated_at": generated_at}

    try:
        with sync_session_factory() as session:
            session.execute(
                text(
                    "UPDATE tenants "
                    "SET settings = jsonb_set("
                    "  COALESCE(settings, '{}'::jsonb), "
                    "  '{p02_website_context}', "
                    "  CAST(:payload AS jsonb), "
                    "  true"
                    ") "
                    "WHERE id = CAST(:tenant_id AS uuid)"
                ),
                {
                    "payload": json.dumps(payload, ensure_ascii=False),
                    "tenant_id": tenant_id,
                },
            )
            session.commit()
        logger.info("p02: website_context für tenant=%s gespeichert", tenant_id)
    except Exception as exc:
        logger.warning("p02: Speichern von website_context fehlgeschlagen (fail-open): %s", exc)


# ---------------------------------------------------------------------------
# Celery Task
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.p02_task.run_p02", bind=True, max_retries=1)
def run_p02(
    self,
    tenant_id: str,
    website_url: str | None = None,
    project_id: str | None = None,
) -> dict:
    """P02-Website-Analyse: fetcht und analysiert die Tenant-Website (additiv, fail-open).

    Args:
        tenant_id:   ID des Tenants (UUID-String).
        website_url: URL der zu analysierenden Website. Ohne URL → skip.
        project_id:  Optionale Projekt-ID (für spätere Erweiterung, wird im Log vermerkt).

    Returns:
        dict mit status='done'|'skipped'|'paused_for_cost', reason bei skip.

    Fail-open-Garantie:
        Kein Exception-Raise nach oben — alle Fehler → Warning-Log + skip-Return.
    """
    # ------------------------------------------------------------------
    # 1. Guard: kein website_url → skip (fail-open, kein Fehler)
    # ------------------------------------------------------------------
    if not website_url or not website_url.strip():
        logger.info("p02: tenant=%s kein website_url → skip", tenant_id)
        return {"status": "skipped", "reason": "no_url"}

    website_url = website_url.strip()

    # ------------------------------------------------------------------
    # 2. Kill-Switch prüfen (wie P01/P03/P04)
    # ------------------------------------------------------------------
    from services.kill_switch import KillSwitchTriggered, check_kill_switch

    try:
        check_kill_switch(tenant_id)
    except KillSwitchTriggered:
        return {"status": "aborted", "reason": "tenant_disabled"}

    run_id = str(uuid.uuid4())
    logger.info(
        "p02 run_id=%s tenant=%s url=%s project=%s", run_id, tenant_id, website_url, project_id
    )

    # ------------------------------------------------------------------
    # 3. Cost-Cap-Vorcheck (fail-open: Fehler beim Check → weiter)
    # ------------------------------------------------------------------
    try:
        import asyncio

        from services.pipeline_llm import estimate_tier_cost, resolve_tier

        _tier, _ = resolve_tier("P02")
        estimated_cost = estimate_tier_cost(_tier, 2000, 500)

        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker as _sm

        from config import settings as _cfg
        from services.cost_cap import CostCapExceeded, CostCapMiddleware
        from services.llm import BudgetExceededError
        from services.rls import tenant_session

        async def _p02_cap_check() -> None:
            _engine = create_async_engine(_cfg.database_url, pool_pre_ping=True)
            _Session = _sm(_engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with tenant_session(_Session, tenant_id) as _sess:
                    await CostCapMiddleware(_sess).check_and_record(tenant_id, estimated_cost)
            finally:
                await _engine.dispose()

        try:
            asyncio.run(_p02_cap_check())
        except (CostCapExceeded, BudgetExceededError):
            logger.warning("p02 run_id=%s tenant=%s: cost cap exceeded → paused", run_id, tenant_id)
            return {"run_id": run_id, "status": "paused_for_cost"}

    except Exception as cap_err:
        # Fail-open: Cost-Cap-Check schlägt fehl → weiter (kein Block)
        logger.warning(
            "p02 run_id=%s: cost-cap check fehlgeschlagen (fail-open): %s", run_id, cap_err
        )

    # ------------------------------------------------------------------
    # 4. Website fetchen
    # ------------------------------------------------------------------
    website_text = _fetch_website_text(website_url)
    if website_text is None:
        logger.info("p02 run_id=%s tenant=%s: fetch fehlgeschlagen → skip", run_id, tenant_id)
        return {"run_id": run_id, "status": "skipped", "reason": "fetch_failed"}

    logger.info(
        "p02 run_id=%s: %d Zeichen Website-Text für %s", run_id, len(website_text), website_url
    )

    # ------------------------------------------------------------------
    # 5. Prompt laden (content-truth falls vorhanden, sonst Platzhalter)
    # ------------------------------------------------------------------
    system_prompt = _load_p02_prompt_if_available()

    # ------------------------------------------------------------------
    # 6. LLM-Call via Seam (kein direkter SDK-Aufruf)
    # ------------------------------------------------------------------
    try:
        user_content = (
            f"Website-URL: {website_url}\n\n" f"<website_text>{website_text}</website_text>"
        )
        res = call_pipeline_llm(
            prompt_key="P02",
            system_prompt=system_prompt,
            user_content=user_content,
            tenant_id=tenant_id,
        )
        raw_text = res.text
        model_id = res.model_id
        logger.info(
            "p02 run_id=%s: LLM-Antwort %d chars, model=%s, cost=%.6f USD",
            run_id,
            len(raw_text),
            model_id,
            res.cost_usd,
        )
    except Exception as llm_err:
        # Fail-open: LLM-Fehler → skip, kein Crash
        logger.warning("p02 run_id=%s: LLM-Call fehlgeschlagen (fail-open): %s", run_id, llm_err)
        return {"run_id": run_id, "status": "skipped", "reason": "llm_failed"}

    # ------------------------------------------------------------------
    # 7. JSON-Parsing (fail-open: kein JSON → raw_text als Fallback-Blob)
    # ------------------------------------------------------------------
    try:
        from services.llm_json import parse_json_from_text

        parsed = parse_json_from_text(raw_text)
    except Exception:
        # Fallback: rohen Text als Blob speichern statt hard-fail
        parsed = {"raw_analysis": raw_text[:2000]}

    context_to_save = {
        "url": website_url,
        "model_id": model_id,
        "run_id": run_id,
        **parsed,
    }

    # ------------------------------------------------------------------
    # 8. Additiv in tenants.settings['p02_website_context'] speichern
    # ------------------------------------------------------------------
    _save_website_context(tenant_id, context_to_save)

    return {
        "run_id": run_id,
        "status": "done",
        "url": website_url,
        "model_id": model_id,
    }
