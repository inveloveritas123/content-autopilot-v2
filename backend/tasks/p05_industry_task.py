"""P05 — Branchen-Research + Industry-Context-Aufbau (Phase 4.4, Issue #141).

Pro Tenant generiert ein LLM-Call eine strukturierte Branchen-Map:
  - top_themen: 5–8 zentrale Themen
  - trigger_woerter: 10–15 Branchen-Vokabular für Relevance-Boost
  - sub_branchen: optional (wenn Tenant in Untersegmenten)
  - typische_kundenfragen: 5 Fragen die Kunden in dieser Branche oft stellen

Wird gespeichert in tenants.industry_context (JSONB). Dann nutzt
services/industry_relevance.py das für Score-Boost in der Ideation.

Trigger:
  - manuell via API: POST /api/tenants/me/industry-refresh
  - Cron: monatlich (Branche ändert sich langsam)
"""
from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "Du bist Branchen-Analyst. Erstelle für die angegebene Branche eine strukturierte "
    "Übersicht mit:\n"
    "- top_themen: Liste von 5-8 zentralen Themen, kurze Stichworte (max 50 chars pro Item)\n"
    "- trigger_woerter: Liste von 10-15 Branchen-Vokabular-Wörtern (Fachbegriffe, "
    "  Kennzahlen, Methoden) — werden für Relevance-Score-Boost genutzt\n"
    "- sub_branchen: Liste optionaler Untersegmente (max 5)\n"
    "- typische_kundenfragen: 5 Fragen die Kunden in dieser Branche typischerweise stellen\n\n"
    "Antworte AUSSCHLIESSLICH mit JSON:\n"
    "{\"top_themen\":[...], \"trigger_woerter\":[...], "
    "\"sub_branchen\":[...], \"typische_kundenfragen\":[...]}"
)


async def _refresh_industry_context_async(tenant_id: str) -> dict:
    from services.llm import llm_service, set_llm_tenant

    set_llm_tenant(tenant_id)
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with SessionMaker() as db:
            row = (await db.execute(
                text("SELECT industry, name FROM tenants WHERE id = CAST(:tid AS uuid)"),
                {"tid": tenant_id},
            )).fetchone()
            if not row:
                return {"status": "error", "reason": "tenant_not_found"}
            if not row.industry:
                return {"status": "skipped", "reason": "no_industry_set"}

            industry = row.industry.strip()
            try:
                result = await llm_service.complete_json(
                    prompt=f"Branche: {industry}\nUnternehmen: {row.name}",
                    system=SYSTEM_PROMPT,
                    model="gemini-flash",
                    purpose="analysis",
                )
            except Exception as exc:  # noqa: BLE001
                return {"status": "error", "reason": str(exc)[:120]}

            # Defensive: validate response shape
            if not isinstance(result, dict):
                return {"status": "error", "reason": "no_dict_response"}
            ctx = {
                "top_themen": list(result.get("top_themen") or [])[:8],
                "trigger_woerter": [str(w).lower().strip() for w in result.get("trigger_woerter") or [] if w][:15],
                "sub_branchen": list(result.get("sub_branchen") or [])[:5],
                "typische_kundenfragen": list(result.get("typische_kundenfragen") or [])[:5],
                "industry_label": industry,
                "generated_at": "now",  # NOW() in DB
            }
            await db.execute(
                text(
                    "UPDATE tenants SET industry_context = CAST(:ctx AS jsonb) "
                    "WHERE id = CAST(:tid AS uuid)"
                ),
                {"ctx": json.dumps(ctx, ensure_ascii=False), "tid": tenant_id},
            )
            await db.commit()
            return {
                "status": "ok",
                "industry": industry,
                "n_themen": len(ctx["top_themen"]),
                "n_trigger": len(ctx["trigger_woerter"]),
            }
    finally:
        await engine.dispose()


@celery_app.task(name="tasks.p05_industry_task.refresh_industry_context", bind=True, max_retries=1)
def refresh_industry_context(self, tenant_id: str) -> dict:
    try:
        return asyncio.run(_refresh_industry_context_async(tenant_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("p05 top-level fail %s: %s", tenant_id, exc)
        return {"status": "error", "reason": str(exc)[:200]}
