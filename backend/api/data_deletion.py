"""DSGVO Art. 17 — Right-to-be-forgotten (Issue #148, Welle E).

4 Lösch-Modi (per Experte 2):
- full              — komplettes Tenant-Konto (Soft-Delete, 30 Tage Recovery)
- memory_selective  — nur memory_chunks (mit Filter older_than_days etc.)
- telegram_purge    — telegram_message_log + telegram-spezifische memory_chunks
- audit_selective   — gezielt einzelne content_pieces / content_ideas / source_items

Workflow:
1. POST /api/me/data-deletion          → soft-delete + recovery_until = NOW()+30d
2. POST /api/me/data-deletion/{id}/recover (innerhalb 30 Tagen) → restore
3. Nightly cron `tasks.deletion_purge_task.purge_expired` → hard-delete
"""
from __future__ import annotations

import datetime
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_MODES = ("full", "memory_selective", "telegram_purge", "audit_selective")
RECOVERY_DAYS = 30


class DeletionRequest(BaseModel):
    mode: str = Field(..., description="full | memory_selective | telegram_purge | audit_selective")
    older_than_days: Optional[int] = Field(None, ge=0, le=3650)
    classification: Optional[str] = Field(None, description="für memory_selective")
    record_ids: Optional[list[str]] = Field(None, description="für audit_selective")
    notes: Optional[str] = Field(None, max_length=1000)


async def _soft_delete_memory(db: AsyncSession, tenant_id, older_than_days, classification) -> int:
    where = ["tenant_id = :tid", "deleted_at IS NULL"]
    params: dict = {"tid": tenant_id}
    if older_than_days is not None:
        where.append("created_at < NOW() - make_interval(days => :days)")
        params["days"] = older_than_days
    if classification:
        where.append("classification = :cls")
        params["cls"] = classification
    result = await db.execute(
        text(f"UPDATE memory_chunks SET deleted_at = NOW() WHERE {' AND '.join(where)}"),
        params,
    )
    return result.rowcount or 0


async def _soft_delete_telegram(db: AsyncSession, tenant_id, older_than_days) -> dict:
    counts: dict = {}
    where = ["tenant_id = :tid", "deleted_at IS NULL", "source_type LIKE 'voice_telegram%'"]
    params: dict = {"tid": tenant_id}
    if older_than_days is not None:
        where.append("created_at < NOW() - make_interval(days => :days)")
        params["days"] = older_than_days
    r = await db.execute(
        text(f"UPDATE memory_chunks SET deleted_at = NOW() WHERE {' AND '.join(where)}"),
        params,
    )
    counts["memory_chunks"] = r.rowcount or 0
    r2 = await db.execute(
        text("DELETE FROM telegram_message_log WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )
    counts["telegram_message_log"] = r2.rowcount or 0
    return counts


async def _soft_delete_audit(db: AsyncSession, tenant_id, record_ids) -> dict:
    counts: dict = {"content_pieces": 0, "content_ideas": 0, "source_items": 0}
    if not record_ids:
        return counts
    for table in ("content_pieces", "content_ideas", "source_items"):
        r = await db.execute(
            text(f"UPDATE {table} SET deleted_at = NOW() "
                 f"WHERE tenant_id = :tid AND id = ANY(:ids) AND deleted_at IS NULL"),
            {"tid": tenant_id, "ids": record_ids},
        )
        counts[table] = r.rowcount or 0
    return counts


async def _soft_delete_full(db: AsyncSession, tenant_id, tenant_name) -> dict:
    counts: dict = {}
    for table in ("memory_chunks", "content_pieces", "content_ideas", "source_items"):
        r = await db.execute(
            text(f"UPDATE {table} SET deleted_at = NOW() "
                 f"WHERE tenant_id = :tid AND deleted_at IS NULL"),
            {"tid": tenant_id},
        )
        counts[table] = r.rowcount or 0
    await db.execute(
        text("UPDATE tenants SET enabled = false, disabled_reason = :r, "
             "disabled_at = NOW(), disabled_by = 'rtbf_request' "
             "WHERE id = :tid"),
        {"tid": tenant_id, "r": f"DSGVO Art. 17 — Soft-Delete für '{tenant_name}'"},
    )
    return counts


@router.post("/me/data-deletion", status_code=201)
async def request_deletion(
    payload: DeletionRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    if payload.mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {VALID_MODES}")

    now = datetime.datetime.utcnow()
    recovery_until = now + datetime.timedelta(days=RECOVERY_DAYS)

    affected: dict = {}
    if payload.mode == "full":
        affected = await _soft_delete_full(db, tenant.id, tenant.name)
    elif payload.mode == "memory_selective":
        n = await _soft_delete_memory(db, tenant.id, payload.older_than_days, payload.classification)
        affected = {"memory_chunks": n}
    elif payload.mode == "telegram_purge":
        affected = await _soft_delete_telegram(db, tenant.id, payload.older_than_days)
    elif payload.mode == "audit_selective":
        affected = await _soft_delete_audit(db, tenant.id, payload.record_ids or [])

    req_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO deletion_requests
                (id, tenant_id, tenant_name_snapshot, mode, payload_filter,
                 status, affected_records, requested_by, requested_at,
                 recovery_until, soft_deleted_at, notes)
            VALUES
                (:id, :tid, :tname, :mode, CAST(:pf AS jsonb),
                 'soft_deleted', CAST(:aff AS jsonb), 'user', :now,
                 :ru, :now, :notes)
        """),
        {
            "id": req_id, "tid": tenant.id, "tname": tenant.name, "mode": payload.mode,
            "pf": __import__("json").dumps({
                "older_than_days": payload.older_than_days,
                "classification": payload.classification,
                "record_ids": payload.record_ids,
            }),
            "aff": __import__("json").dumps(affected),
            "now": now, "ru": recovery_until, "notes": payload.notes,
        },
    )
    await db.commit()

    return {
        "id": str(req_id),
        "mode": payload.mode,
        "status": "soft_deleted",
        "affected": affected,
        "recovery_until": recovery_until.isoformat(),
        "recovery_days": RECOVERY_DAYS,
        "message": f"Daten sind soft-gelöscht. Du kannst sie bis {recovery_until.date()} wiederherstellen.",
    }


@router.get("/me/data-deletion")
async def list_deletions(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        text("""
            SELECT id, mode, status, affected_records, requested_at,
                   recovery_until, soft_deleted_at, hard_deleted_at, recovered_at, notes
            FROM deletion_requests
            WHERE tenant_id = :tid
            ORDER BY requested_at DESC LIMIT 50
        """),
        {"tid": tenant.id},
    )).fetchall()
    return {
        "history": [{
            "id": str(r.id),
            "mode": r.mode,
            "status": r.status,
            "affected": r.affected_records,
            "requested_at": r.requested_at.isoformat() if r.requested_at else None,
            "recovery_until": r.recovery_until.isoformat() if r.recovery_until else None,
            "soft_deleted_at": r.soft_deleted_at.isoformat() if r.soft_deleted_at else None,
            "hard_deleted_at": r.hard_deleted_at.isoformat() if r.hard_deleted_at else None,
            "recovered_at": r.recovered_at.isoformat() if r.recovered_at else None,
            "notes": r.notes,
        } for r in rows]
    }


@router.post("/me/data-deletion/{req_id}/recover")
async def recover_deletion(
    req_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        text("""
            SELECT id, mode, status, recovery_until, affected_records
            FROM deletion_requests
            WHERE id = :id AND tenant_id = :tid
        """),
        {"id": req_id, "tid": tenant.id},
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="deletion request not found")
    if row.status != "soft_deleted":
        raise HTTPException(status_code=409, detail=f"cannot recover: status={row.status}")
    if row.recovery_until and row.recovery_until < datetime.datetime.now(datetime.timezone.utc):
        raise HTTPException(status_code=410, detail="recovery period expired")

    affected: dict = row.affected_records or {}
    restored: dict = {}
    for table in ("memory_chunks", "content_pieces", "content_ideas", "source_items"):
        if affected.get(table, 0) > 0:
            r = await db.execute(
                text(f"UPDATE {table} SET deleted_at = NULL "
                     f"WHERE tenant_id = :tid AND deleted_at IS NOT NULL"),
                {"tid": tenant.id},
            )
            restored[table] = r.rowcount or 0
    if row.mode == "full":
        await db.execute(
            text("UPDATE tenants SET enabled = true, disabled_reason = NULL, "
                 "disabled_at = NULL, disabled_by = NULL WHERE id = :tid"),
            {"tid": tenant.id},
        )

    await db.execute(
        text("UPDATE deletion_requests SET status = 'recovered', recovered_at = NOW() WHERE id = :id"),
        {"id": req_id},
    )
    await db.commit()
    return {"id": req_id, "status": "recovered", "restored": restored}


@router.get("/me/data-deletion/{req_id}")
async def get_deletion(
    req_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        text("""
            SELECT id, mode, status, affected_records, requested_at,
                   recovery_until, soft_deleted_at, hard_deleted_at, recovered_at, notes
            FROM deletion_requests
            WHERE id = :id AND tenant_id = :tid
        """),
        {"id": req_id, "tid": tenant.id},
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="deletion request not found")
    return {
        "id": str(row.id),
        "mode": row.mode,
        "status": row.status,
        "affected": row.affected_records,
        "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "recovery_until": row.recovery_until.isoformat() if row.recovery_until else None,
        "soft_deleted_at": row.soft_deleted_at.isoformat() if row.soft_deleted_at else None,
        "hard_deleted_at": row.hard_deleted_at.isoformat() if row.hard_deleted_at else None,
        "recovered_at": row.recovered_at.isoformat() if row.recovered_at else None,
        "notes": row.notes,
    }
