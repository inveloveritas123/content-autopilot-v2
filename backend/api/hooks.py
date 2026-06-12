"""Hook-Library-API (Phase 7.4, Issue #142).

Endpoints:
  GET    /api/hooks/library           — Liste der Hooks pro Tenant
  POST   /api/hooks/library           — manuell einen Hook hinzufügen
  DELETE /api/hooks/library/{id}      — Hook löschen
  POST   /api/hooks/library/import    — aus content_pieces importieren
                                        (top-N nach performance)
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant

router = APIRouter(prefix="/hooks", tags=["hooks"])


HOOK_TYPES = {"general", "hook", "story", "these", "manual"}


class HookIn(BaseModel):
    hook_text: str = Field(..., min_length=5, max_length=500)
    hook_type: str = "manual"
    metadata: dict | None = None


@router.get("/library")
async def list_hooks(
    hook_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    sort: str = Query("performance", regex="^(performance|recent|usage)$"),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    where = ["tenant_id = :tid"]
    params: dict = {"tid": tenant.id, "lim": limit}
    if hook_type:
        if hook_type not in HOOK_TYPES:
            raise HTTPException(400, f"Unbekannter hook_type — erlaubt: {sorted(HOOK_TYPES)}")
        where.append("hook_type = :ht")
        params["ht"] = hook_type
    order_clause = {
        "performance": "performance_score DESC, created_at DESC",
        "recent": "created_at DESC",
        "usage": "used_count DESC, performance_score DESC",
    }[sort]
    rows = (
        await db.execute(
            text(
                f"SELECT id, source_piece_id, hook_text, hook_type, performance_score, "
                f"       used_count, last_used_at, metadata, created_at "
                f"FROM hook_library WHERE {' AND '.join(where)} "
                f"ORDER BY {order_clause} LIMIT :lim"
            ),
            params,
        )
    ).fetchall()
    return [
        {
            "id": str(r.id),
            "source_piece_id": str(r.source_piece_id) if r.source_piece_id else None,
            "hook_text": r.hook_text,
            "hook_type": r.hook_type,
            "performance_score": float(r.performance_score or 0),
            "used_count": int(r.used_count or 0),
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            "metadata": dict(r.metadata or {}),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/library")
async def add_hook(
    payload: HookIn,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    if payload.hook_type not in HOOK_TYPES:
        raise HTTPException(400, "Unbekannter hook_type")
    new_id = (
        await db.execute(
            text(
                "INSERT INTO hook_library (tenant_id, hook_text, hook_type, metadata) "
                "VALUES (:tid, :h, :ht, CAST(:m AS jsonb)) RETURNING id"
            ),
            {
                "tid": tenant.id,
                "h": payload.hook_text.strip(),
                "ht": payload.hook_type,
                "m": json.dumps(payload.metadata or {}, ensure_ascii=False),
            },
        )
    ).fetchone()
    await db.commit()
    return {"id": str(new_id.id), "status": "ok"}


@router.delete("/library/{hook_id}")
async def delete_hook(
    hook_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        text(
            "DELETE FROM hook_library WHERE id = CAST(:id AS uuid) AND tenant_id = :tid "
            "RETURNING id"
        ),
        {"id": hook_id, "tid": tenant.id},
    )
    if not res.fetchone():
        raise HTTPException(404, "Hook nicht gefunden")
    await db.commit()
    return {"status": "ok"}


@router.post("/library/import")
async def import_from_pieces(
    limit: int = Query(20, ge=1, le=100),
    min_chars: int = Query(20, ge=10),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Importiert die ersten N Zeichen jedes content_pieces als Hook.

    Idempotent: skip wenn source_piece_id bereits in hook_library.
    Performance-Score aus content_performances falls verfügbar, sonst 0.
    """
    rows = (
        await db.execute(
            text(
                "SELECT cp.id, cp.content_text, cp.category, "
                "       COALESCE(MAX(perf.engagement_rate), 0) AS perf_score "
                "FROM content_pieces cp "
                "LEFT JOIN content_performances perf ON perf.content_piece_id = cp.id "
                "WHERE cp.tenant_id = :tid AND cp.status IN ('draft', 'approved', 'published') "
                "  AND LENGTH(COALESCE(cp.content_text, '')) >= :minc "
                "  AND cp.id NOT IN ("
                "    SELECT source_piece_id FROM hook_library "
                "    WHERE source_piece_id IS NOT NULL AND tenant_id = :tid"
                "  ) "
                "GROUP BY cp.id, cp.content_text, cp.category "
                "ORDER BY perf_score DESC NULLS LAST, cp.created_at DESC "
                "LIMIT :lim"
            ),
            {"tid": tenant.id, "minc": min_chars, "lim": limit},
        )
    ).fetchall()

    imported = 0
    for r in rows:
        # Erste Zeile / 200 Zeichen als Hook
        first_line = (r.content_text or "").split("\n")[0].strip()
        hook = first_line[:200] or (r.content_text or "")[:200]
        if not hook:
            continue
        await db.execute(
            text(
                "INSERT INTO hook_library "
                "(tenant_id, source_piece_id, hook_text, hook_type, performance_score, metadata) "
                "VALUES (:tid, :pid, :h, 'general', :ps, CAST(:m AS jsonb))"
            ),
            {
                "tid": tenant.id,
                "pid": r.id,
                "h": hook,
                "ps": float(r.perf_score or 0),
                "m": json.dumps({"imported": True, "category": r.category}, ensure_ascii=False),
            },
        )
        imported += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "scanned": len(rows)}


@router.post("/library/{hook_id}/track-use")
async def track_hook_use(
    hook_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Wird vom P12-Generator aufgerufen wenn ein Hook aus der Library benutzt wird."""
    res = await db.execute(
        text(
            "UPDATE hook_library SET used_count = used_count + 1, last_used_at = now() "
            "WHERE id = CAST(:id AS uuid) AND tenant_id = :tid "
            "RETURNING used_count"
        ),
        {"id": hook_id, "tid": tenant.id},
    )
    row = res.fetchone()
    if not row:
        raise HTTPException(404, "Hook nicht gefunden")
    await db.commit()
    return {"status": "ok", "used_count": row.used_count}
