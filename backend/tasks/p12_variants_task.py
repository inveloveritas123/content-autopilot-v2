"""P12-Variants-Task (Phase 4.2, Issue #147).

Generiert 3 Aufhänger-Varianten (hook/story/these) für eine Idee
und persistiert sie in idea_variants.

Wird aus dem Pipeline-Pump aufgerufen oder manuell via UI-Trigger
„Regenerate Varianten".
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

ALLOWED_VARIANT_TYPES = {"hook", "story", "these"}


async def _generate_variants_async(idea_id: str) -> dict:
    """Lädt die Idee, ruft LLM, persistiert die 3 Varianten."""
    from services.llm import llm_service, set_llm_tenant

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with SessionMaker() as db:
            # Lade Idea + Tenant — Schema content_ideas: title, description, angle, hook_suggestion
            idea_row = (await db.execute(
                text(
                    "SELECT id, tenant_id, title, description, angle, hook_suggestion, "
                    "       source_quotes, source_context "
                    "FROM content_ideas WHERE id = CAST(:id AS uuid)"
                ),
                {"id": idea_id},
            )).fetchone()
            if not idea_row:
                return {"status": "error", "reason": "idea_not_found"}

            tenant_id = str(idea_row.tenant_id)
            set_llm_tenant(tenant_id)

            # Voice-Profile + Customer-Context-Snippet für Kontext
            quotes_excerpt = ""
            try:
                if idea_row.source_quotes:
                    qs = idea_row.source_quotes if isinstance(idea_row.source_quotes, list) else []
                    quotes_excerpt = " | ".join(str(q)[:120] for q in qs[:3])
            except Exception:
                pass

            ctx = {
                "idea": {
                    "title": idea_row.title,
                    "description": (idea_row.description or "")[:600],
                    "angle": idea_row.angle,
                    "hook_suggestion": idea_row.hook_suggestion,
                    "source_quotes_excerpt": quotes_excerpt[:400],
                },
            }
            # voice_profile-Lookup in Savepoint — bei Schema-Drift kein Transaktions-Abort
            try:
                async with db.begin_nested():
                    vp_row = (await db.execute(
                        text(
                            "SELECT payload FROM voice_profile_versions "
                            "WHERE tenant_id = CAST(:tid AS uuid) AND is_active = true "
                            "ORDER BY version DESC LIMIT 1"
                        ),
                        {"tid": tenant_id},
                    )).fetchone()
                    if vp_row and vp_row.payload:
                        ctx["voice_profile"] = vp_row.payload
            except Exception:
                pass  # voice_profile_versions evtl. nicht im Schema — defensive

            system_prompt = _load_variants_system_prompt()
            try:
                response = await llm_service.complete_json(
                    prompt=f"Idee + Kontext:\n{json.dumps(ctx, ensure_ascii=False, indent=2)}",
                    system=system_prompt,
                    model="claude-sonnet",
                    purpose="creative",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("p12_variants LLM-Call fehlgeschlagen: %s", exc)
                return {"status": "error", "reason": str(exc)[:120]}

            variants = response.get("variants") if isinstance(response, dict) else None
            if not isinstance(variants, list) or not variants:
                logger.warning("p12_variants: kein variants-Array im Response")
                return {"status": "error", "reason": "no_variants_in_response"}

            # Validate + dedupe + insert
            seen_types = set()
            inserted = []
            for v in variants:
                if not isinstance(v, dict):
                    continue
                vtype = (v.get("type") or "").strip().lower()
                if vtype not in ALLOWED_VARIANT_TYPES or vtype in seen_types:
                    continue
                hook_text = (v.get("hook_text") or "").strip()
                body_outline = (v.get("body_outline") or "").strip()
                if not hook_text or not body_outline:
                    continue
                seen_types.add(vtype)
                # Upsert: bestehende Variante gleichen Typs überschreiben
                await db.execute(
                    text(
                        "INSERT INTO idea_variants "
                        "(idea_id, tenant_id, variant_type, hook_text, body_outline) "
                        "VALUES (CAST(:idea_id AS uuid), CAST(:tid AS uuid), :vt, :h, :b) "
                        "ON CONFLICT (idea_id, variant_type) DO UPDATE SET "
                        "  hook_text = EXCLUDED.hook_text, "
                        "  body_outline = EXCLUDED.body_outline, "
                        "  is_chosen = false, chosen_at = NULL, "
                        "  created_at = now()"
                    ),
                    {"idea_id": idea_id, "tid": tenant_id, "vt": vtype,
                     "h": hook_text[:1000], "b": body_outline[:3000]},
                )
                inserted.append(vtype)

            await db.commit()

            if not inserted:
                return {"status": "error", "reason": "no_valid_variants"}
            return {"status": "ok", "inserted": inserted, "idea_id": idea_id}
    finally:
        await engine.dispose()


def _load_variants_system_prompt() -> str:
    """Lädt p12_variants.md aus dem Prompts-Ordner (Container-Pfad /app/prompts)."""
    from pathlib import Path
    paths = [
        Path("/app/prompts/p12_variants.md"),
        Path(__file__).parent.parent / "prompts" / "p12_variants.md",
    ]
    for p in paths:
        if p.exists():
            content = p.read_text(encoding="utf-8")
            # System-Prompt-Sektion herausnehmen
            if "## System-Prompt" in content:
                _, after = content.split("## System-Prompt", 1)
                if "## User-Prompt" in after:
                    sys_text, _ = after.split("## User-Prompt", 1)
                    return sys_text.strip()
            return content
    # Fallback
    return (
        "Generiere 3 Aufhänger-Varianten (hook|story|these) als JSON. "
        '{"variants":[{"type":"hook","hook_text":"...","body_outline":"..."}, ...]}'
    )


@celery_app.task(name="tasks.p12_variants_task.generate_variants", bind=True, max_retries=1)
def generate_variants(self, idea_id: str) -> dict:
    try:
        return asyncio.run(_generate_variants_async(idea_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("generate_variants top-level: %s", exc)
        return {"status": "error", "reason": str(exc)[:200]}
