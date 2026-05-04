"""Research-Findings-API (Phase 6.1, Issue #141)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/findings")
async def list_research_findings(
    status_filter: str = Query("active", regex="^(active|dismissed|used|all)$"),
    category: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Liste der Research-Befunde für den Tenant."""
    where_parts = ["tenant_id = :tid"]
    params: dict = {"tid": tenant.id, "lim": limit}
    if status_filter != "all":
        where_parts.append("status = :st")
        params["st"] = status_filter
    if category:
        where_parts.append("category = :cat")
        params["cat"] = category
    sql = (
        "SELECT id, source_item_id, category, title, summary, source_url, "
        "       source_publisher, source_date, impact_rating, impact_justification, "
        "       hooks, status, created_at "
        f"FROM research_findings WHERE {' AND '.join(where_parts)} "
        "ORDER BY created_at DESC LIMIT :lim"
    )
    rows = (await db.execute(text(sql), params)).fetchall()
    return [
        {
            "id": str(r.id),
            "source_item_id": str(r.source_item_id) if r.source_item_id else None,
            "category": r.category,
            "title": r.title,
            "summary": r.summary,
            "source_url": r.source_url,
            "source_publisher": r.source_publisher,
            "source_date": r.source_date.isoformat() if r.source_date else None,
            "impact_rating": r.impact_rating,
            "impact_justification": r.impact_justification,
            "hooks": list(r.hooks or []),
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/findings/{finding_id}/dismiss")
async def dismiss_research_finding(
    finding_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        text(
            "UPDATE research_findings SET status='dismissed', dismissed_at=now() "
            "WHERE id = CAST(:id AS uuid) AND tenant_id = :tid AND status='active' "
            "RETURNING id"
        ),
        {"id": finding_id, "tid": tenant.id},
    )
    row = res.fetchone()
    if not row:
        raise HTTPException(404, "Befund nicht gefunden oder bereits dismissed")
    await db.commit()
    return {"status": "ok"}


@router.post("/findings/{finding_id}/use-as-idea")
async def use_finding_as_idea(
    finding_id: str,
    hook_index: int = Query(0, ge=0, le=2),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Erstellt eine ContentIdea aus dem Befund + dem gewählten Hook."""
    finding = (await db.execute(
        text(
            "SELECT source_item_id, title, summary, hooks "
            "FROM research_findings WHERE id = CAST(:id AS uuid) AND tenant_id = :tid"
        ),
        {"id": finding_id, "tid": tenant.id},
    )).fetchone()
    if not finding:
        raise HTTPException(404, "Befund nicht gefunden")
    if not finding.source_item_id:
        raise HTTPException(400, "Befund hat keine source_item-Verknüpfung")
    hooks = list(finding.hooks or [])
    chosen_hook = hooks[hook_index] if hook_index < len(hooks) else (hooks[0] if hooks else None)

    new_idea_id = (await db.execute(
        text(
            "INSERT INTO content_ideas "
            "(source_item_id, tenant_id, title, description, angle, hook_suggestion, "
            " relevance_score, priority, status) "
            "VALUES (:sid, :tid, :title, :desc, 'research', :hook, 8.0, '1', 'new') "
            "RETURNING id"
        ),
        {
            "sid": finding.source_item_id,
            "tid": tenant.id,
            "title": finding.title[:500],
            "desc": (finding.summary or "")[:1000],
            "hook": chosen_hook,
        },
    )).fetchone()

    await db.execute(
        text("UPDATE research_findings SET status='used' WHERE id = CAST(:id AS uuid)"),
        {"id": finding_id},
    )
    await db.commit()
    return {"status": "ok", "idea_id": str(new_idea_id.id), "hook_used": chosen_hook}
