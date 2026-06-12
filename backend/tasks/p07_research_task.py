"""P07 — Themen-Research mit Hook-Vorschlägen (Phase 6.1, Issue #141).

Pragmatischer Ansatz für die erste Iteration:
- Statt Live-Web-Search nutzt P07 die source_items der letzten 7 Tage
  (RSS-Feeds + YouTube-Transkripte) als Research-Pool. Tenant hat dort
  bereits kuratiert was er als relevant ansieht.
- Pro Item: LLM-Klassifikator nach 6 Master-MD-Kategorien + 3 Hook-
  Vorschläge im Voice-Profil-Stil + Impact-Rating.
- Source-traceable: source_item_id als FK + source_url + Datum.

Master-MD-Constraints respektiert:
- Keine synthesis über mehrere Sources (1 finding = 1 source_item)
- Title/Summary direkt aus source_item (nicht extrapoliert)
- Concrete source_url-Link
- Quality-Filter: nur Items mit ≥ 200 chars Transcript/Description

Cron: Dienstag + Freitag 06:30 Europe/Berlin (~2× pro Woche).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = {
    "rules_constraints",
    "demand_behavior",
    "tools_methods",
    "competition_market",
    "costs_resources",
    "emerging_topics",
}
ALLOWED_IMPACTS = {"positive", "neutral", "negative"}

LOOKBACK_DAYS = 7
MAX_ITEMS_PER_TENANT = 25
MIN_TEXT_CHARS = 200


def _system_prompt(voice_profile_excerpt: str = "") -> str:
    voice_part = (
        f"\nBrand-Voice-Hinweise: {voice_profile_excerpt[:600]}" if voice_profile_excerpt else ""
    )
    return (
        "Du bist Research-Analyst. Klassifiziere die News-Quelle in EINE der "
        "folgenden Kategorien:\n"
        "- 'rules_constraints' (Regulierung, Compliance)\n"
        "- 'demand_behavior' (Kundenverhalten, Marktnachfrage)\n"
        "- 'tools_methods' (Tools, Methoden, Prozesse)\n"
        "- 'competition_market' (Wettbewerber, Marktstruktur)\n"
        "- 'costs_resources' (Kosten, Ressourcen, Verfügbarkeit)\n"
        "- 'emerging_topics' (aktuell breit diskutierte Themen)\n\n"
        "Generiere 3 LinkedIn-Hooks im persönlichen Stil des Unternehmers — "
        "kein Clickbait, source-grounded, max 200 Zeichen pro Hook."
        + voice_part
        + "\n\nAntworte AUSSCHLIESSLICH mit JSON:\n"
        '{"category":"...", "impact_rating":"positive|neutral|negative", '
        '"impact_justification":"...", "hooks":["...","...","..."]}'
    )


async def _process_item_async(
    db: AsyncSession,
    tenant_id: str,
    item_row,
    voice_profile_excerpt: str,
) -> str | None:
    """Verarbeitet ein source_item zu einem research_findings-Eintrag."""
    from services.llm import llm_service, set_llm_tenant

    set_llm_tenant(tenant_id)

    text_content = (item_row.transcript_text or item_row.description or "")[:3000]
    if len(text_content) < MIN_TEXT_CHARS:
        return None

    title = (item_row.title or "(ohne Titel)")[:500]
    user_payload = {
        "title": title,
        "content": text_content,
        "source_url": item_row.url,
        "publisher": item_row.source_name,
        "published_at": item_row.published_at.isoformat() if item_row.published_at else None,
    }

    try:
        result = await llm_service.complete_json(
            prompt=json.dumps(user_payload, ensure_ascii=False, indent=2),
            system=_system_prompt(voice_profile_excerpt),
            model="gemini-flash",
            purpose="analysis",
        )
    except Exception as exc:
        logger.info("p07 LLM-Call skipped (%s): %s", item_row.id, str(exc)[:80])
        return None

    if not isinstance(result, dict):
        return None
    cat = (result.get("category") or "").strip().lower()
    if cat not in ALLOWED_CATEGORIES:
        logger.info("p07: ungültige Kategorie %r — skip", cat)
        return None
    impact = (result.get("impact_rating") or "neutral").strip().lower()
    if impact not in ALLOWED_IMPACTS:
        impact = "neutral"
    hooks = result.get("hooks") or []
    if not isinstance(hooks, list):
        hooks = []
    hooks = [str(h).strip()[:300] for h in hooks if isinstance(h, str) and h.strip()][:3]
    if not hooks:
        return None

    summary = text_content[:600].strip()
    impact_justification = (result.get("impact_justification") or "")[:500]

    # Idempotent: Skip wenn schon ein finding für dieses item existiert
    existing = (
        await db.execute(
            text(
                "SELECT id FROM research_findings "
                "WHERE source_item_id = :sid AND tenant_id = CAST(:tid AS uuid) "
                "LIMIT 1"
            ),
            {"sid": item_row.id, "tid": tenant_id},
        )
    ).fetchone()
    if existing:
        return None

    finding = (
        await db.execute(
            text(
                "INSERT INTO research_findings "
                "(tenant_id, source_item_id, category, title, summary, source_url, "
                " source_publisher, source_date, impact_rating, impact_justification, hooks) "
                "VALUES (CAST(:tid AS uuid), :sid, :cat, :title, :summary, :url, "
                "        :pub, :pdate, :impact, :imp_just, CAST(:hooks AS jsonb)) "
                "RETURNING id"
            ),
            {
                "tid": tenant_id,
                "sid": item_row.id,
                "cat": cat,
                "title": title,
                "summary": summary,
                "url": (item_row.url or "")[:2000] or None,
                "pub": (item_row.source_name or "")[:200] or None,
                "pdate": item_row.published_at,
                "impact": impact,
                "imp_just": impact_justification,
                "hooks": json.dumps(hooks, ensure_ascii=False),
            },
        )
    ).fetchone()
    await db.commit()
    return str(finding.id) if finding else None


async def _run_for_tenant_async(tenant_id: str) -> dict:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    cutoff = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    inserted = 0
    skipped = 0
    try:
        async with SessionMaker() as db:
            # Voice-Profile-Snippet (savepoint-isoliert)
            voice_excerpt = ""
            try:
                async with db.begin_nested():
                    vp = (
                        await db.execute(
                            text(
                                "SELECT payload FROM voice_profile_versions "
                                "WHERE tenant_id = CAST(:tid AS uuid) AND is_active = true "
                                "ORDER BY version DESC LIMIT 1"
                            ),
                            {"tid": tenant_id},
                        )
                    ).fetchone()
                    if vp and vp.payload:
                        voice_excerpt = json.dumps(vp.payload, ensure_ascii=False)[:800]
            except Exception:
                pass

            # source_items aus den letzten 7 Tagen, mit Transkript/Beschreibung
            rows = (
                await db.execute(
                    text(
                        "SELECT si.id, si.title, si.url, si.transcript_text, si.description, "
                        "       si.published_at, s.name AS source_name "
                        "FROM source_items si "
                        "LEFT JOIN sources s ON s.id = si.source_id "
                        "WHERE si.tenant_id = CAST(:tid AS uuid) "
                        "  AND si.published_at >= :cut "
                        "  AND (LENGTH(COALESCE(si.transcript_text, '')) >= :minc "
                        "       OR LENGTH(COALESCE(si.description, '')) >= :minc) "
                        "ORDER BY si.published_at DESC "
                        "LIMIT :lim"
                    ),
                    {
                        "tid": tenant_id,
                        "cut": cutoff,
                        "minc": MIN_TEXT_CHARS,
                        "lim": MAX_ITEMS_PER_TENANT,
                    },
                )
            ).fetchall()

            for r in rows:
                fid = await _process_item_async(db, tenant_id, r, voice_excerpt)
                if fid:
                    inserted += 1
                else:
                    skipped += 1
    finally:
        await engine.dispose()
    return {"tenant_id": tenant_id, "inserted": inserted, "skipped": skipped}


def _push_research_to_telegram(tenant_id: str, inserted: int) -> None:
    """Nach dem P07-Lauf neue Findings per Telegram an den Tenant schicken (Issue #35)."""
    if inserted <= 0:
        return
    try:
        from api.telegram import _send_telegram_message
        from models.base import sync_session_factory

        with sync_session_factory() as db:
            link = db.execute(
                text(
                    "SELECT telegram_chat_id FROM tenant_telegram_link "
                    "WHERE tenant_id = CAST(:tid AS uuid) AND status = 'active' LIMIT 1"
                ),
                {"tid": tenant_id},
            ).fetchone()
            if not link:
                return
            chat_id: int = link.telegram_chat_id

            findings = db.execute(
                text(
                    "SELECT title, hooks FROM research_findings "
                    "WHERE tenant_id = CAST(:tid AS uuid) AND status = 'active' "
                    "ORDER BY created_at DESC LIMIT 3"
                ),
                {"tid": tenant_id},
            ).fetchall()

        lines = [f"🔍 {inserted} neue Research-Vorschläge sind verfügbar:\n"]
        for i, f in enumerate(findings, 1):
            hooks = f.hooks if isinstance(f.hooks, list) else []
            first_hook = hooks[0] if hooks else ""
            lines.append(f"{i}. {f.title[:100]}")
            if first_hook:
                lines.append(f'   → „{first_hook[:120]}"')
        lines.append("\nAlle Vorschläge im Dashboard unter Research-Findings.")
        _send_telegram_message(chat_id, "\n".join(lines))
    except Exception as exc:
        logger.warning("p07 telegram push failed for %s: %s", tenant_id, exc)


@celery_app.task(name="tasks.p07_research_task.run_research_for_tenant", bind=True, max_retries=1)
def run_research_for_tenant(self, tenant_id: str) -> dict:
    try:
        result = asyncio.run(_run_for_tenant_async(tenant_id))
        _push_research_to_telegram(tenant_id, result.get("inserted", 0))
        return result
    except Exception as exc:
        logger.warning("p07 top-level fail %s: %s", tenant_id, exc)
        return {"status": "error", "reason": str(exc)[:200]}


@celery_app.task(name="tasks.p07_research_task.run_research_all_tenants", bind=True, max_retries=0)
def run_research_all_tenants(self) -> dict:
    """Cron-Task: läuft 2× pro Woche, dispatcht pro aktiver Tenant."""
    from models.base import sync_session_factory

    with sync_session_factory() as db:
        rows = db.execute(
            text(
                "SELECT id FROM tenants WHERE settings->>'research_enabled' IS DISTINCT FROM 'false'"
            )
        ).fetchall()
    dispatched = 0
    for r in rows:
        try:
            run_research_for_tenant.apply_async(args=[str(r[0])])
            dispatched += 1
        except Exception as exc:
            logger.warning("p07 dispatch %s failed: %s", r[0], exc)
    return {"dispatched": dispatched}
