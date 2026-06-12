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
import json
import logging
import uuid

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

# Critical #1: Statische Whitelist aller Soft-Delete-Tabellen.
# Schlüssel = Tabellenname, Wert = SQL-Statement für Soft-Delete.
# KEIN f-String mit variablem Tabellennamen — verhindert SQL-Injection
# wenn die Tabellenliste je aus einer Konfigurationsquelle befüllt wird.
_SOFT_DELETE_TABLES: dict[str, str] = {
    "memory_chunks": (
        "UPDATE memory_chunks "
        "SET deleted_at = NOW(), deletion_request_id = :req_id "
        "WHERE tenant_id = :tid AND deleted_at IS NULL"
    ),
    "content_pieces": (
        "UPDATE content_pieces "
        "SET deleted_at = NOW(), deletion_request_id = :req_id "
        "WHERE tenant_id = :tid AND deleted_at IS NULL"
    ),
    "content_ideas": (
        "UPDATE content_ideas "
        "SET deleted_at = NOW(), deletion_request_id = :req_id "
        "WHERE tenant_id = :tid AND deleted_at IS NULL"
    ),
    "source_items": (
        "UPDATE source_items "
        "SET deleted_at = NOW(), deletion_request_id = :req_id "
        "WHERE tenant_id = :tid AND deleted_at IS NULL"
    ),
    # Critical #4: llm_call_logs in Cascade einbeziehen (DSGVO Art. 17)
    "llm_call_logs": (
        "UPDATE llm_call_logs "
        "SET deleted_at = NOW(), deletion_request_id = :req_id "
        "WHERE tenant_id = :tid AND deleted_at IS NULL"
    ),
}

# M1: Statische Whitelist für _soft_delete_audit — kein f-String mit variablem Tabellennamen.
# Pattern identisch zu _SOFT_DELETE_TABLES (Critical #1).
_AUDIT_TABLES_SOFT_DELETE: dict[str, str] = {
    "content_pieces": (
        "UPDATE content_pieces "
        "SET deleted_at = NOW(), deletion_request_id = :req_id "
        "WHERE tenant_id = :tid AND id = ANY(:ids) AND deleted_at IS NULL"
    ),
    "content_ideas": (
        "UPDATE content_ideas "
        "SET deleted_at = NOW(), deletion_request_id = :req_id "
        "WHERE tenant_id = :tid AND id = ANY(:ids) AND deleted_at IS NULL"
    ),
    "source_items": (
        "UPDATE source_items "
        "SET deleted_at = NOW(), deletion_request_id = :req_id "
        "WHERE tenant_id = :tid AND id = ANY(:ids) AND deleted_at IS NULL"
    ),
}

# M2: Statische Whitelist für recover_deletion — kein f-String mit variablem Tabellennamen.
# telegram_message_log eingeschlossen (M5: Recovery-Symmetrie via deletion_request_id FK).
_RECOVER_TABLES: dict[str, str] = {
    "memory_chunks": (
        "UPDATE memory_chunks SET deleted_at = NULL, deletion_request_id = NULL "
        "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    "content_pieces": (
        "UPDATE content_pieces SET deleted_at = NULL, deletion_request_id = NULL "
        "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    "content_ideas": (
        "UPDATE content_ideas SET deleted_at = NULL, deletion_request_id = NULL "
        "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    "source_items": (
        "UPDATE source_items SET deleted_at = NULL, deletion_request_id = NULL "
        "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    "llm_call_logs": (
        "UPDATE llm_call_logs SET deleted_at = NULL, deletion_request_id = NULL "
        "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    # M5: telegram_message_log Recovery — erfordert deletion_request_id-Spalte
    # (Migration 047 erweitert). Ohne diese Migration bleibt Recovery ein no-op für diese Tabelle.
    "telegram_message_log": (
        "UPDATE telegram_message_log SET deleted_at = NULL, deletion_request_id = NULL "
        "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
}


class DeletionRequest(BaseModel):
    mode: str = Field(..., description="full | memory_selective | telegram_purge | audit_selective")
    older_than_days: int | None = Field(None, ge=0, le=3650)
    classification: str | None = Field(None, description="für memory_selective")
    record_ids: list[str] | None = Field(None, description="für audit_selective")
    notes: str | None = Field(None, max_length=1000)


async def _soft_delete_memory(
    db: AsyncSession, tenant_id, older_than_days, classification, req_id
) -> int:
    where = ["tenant_id = :tid", "deleted_at IS NULL"]
    params: dict = {"tid": tenant_id, "req_id": req_id}
    if older_than_days is not None:
        where.append("created_at < NOW() - make_interval(days => :days)")
        params["days"] = older_than_days
    if classification:
        where.append("classification = :cls")
        params["cls"] = classification
    # M3: f-String-Prefix entfernt — Tabellenname ist hartcodiert, kein f-String nötig.
    # WHERE-Bedingungen werden als parametrisierte Bind-Variablen eingefügt.
    result = await db.execute(
        text(
            "UPDATE memory_chunks "
            "SET deleted_at = NOW(), deletion_request_id = :req_id "
            "WHERE " + " AND ".join(where)
        ),
        params,
    )
    return result.rowcount or 0


async def _soft_delete_telegram(db: AsyncSession, tenant_id, older_than_days, req_id) -> dict:
    counts: dict = {}
    where = [
        "tenant_id = :tid",
        "deleted_at IS NULL",
        "source_type LIKE 'voice_telegram%'",
    ]
    params: dict = {"tid": tenant_id, "req_id": req_id}
    if older_than_days is not None:
        where.append("created_at < NOW() - make_interval(days => :days)")
        params["days"] = older_than_days
    # M3: f-String-Prefix entfernt — Tabellenname ist hartcodiert, kein f-String nötig.
    r = await db.execute(
        text(
            "UPDATE memory_chunks "
            "SET deleted_at = NOW(), deletion_request_id = :req_id "
            "WHERE " + " AND ".join(where)
        ),
        params,
    )
    counts["memory_chunks"] = r.rowcount or 0
    # M5: telegram_message_log soft-delete mit deletion_request_id setzen
    # (statt hard-DELETE) — ermöglicht Recovery via _RECOVER_TABLES.
    # Erfordert: Migration 047 erweitert telegram_message_log um deleted_at + deletion_request_id.
    r2 = await db.execute(
        text(
            "UPDATE telegram_message_log "
            "SET deleted_at = NOW(), deletion_request_id = :req_id "
            "WHERE tenant_id = :tid AND deleted_at IS NULL"
        ),
        {"tid": tenant_id, "req_id": req_id},
    )
    counts["telegram_message_log"] = r2.rowcount or 0
    return counts


async def _soft_delete_audit(db: AsyncSession, tenant_id, record_ids, req_id) -> dict:
    counts: dict = {"content_pieces": 0, "content_ideas": 0, "source_items": 0}
    if not record_ids:
        return counts
    # M1: f-String-Loop durch statische Whitelist _AUDIT_TABLES_SOFT_DELETE ersetzt.
    # Pattern identisch zu _soft_delete_full / _SOFT_DELETE_TABLES (Critical #1).
    for table, stmt in _AUDIT_TABLES_SOFT_DELETE.items():
        r = await db.execute(
            text(stmt),
            {"tid": tenant_id, "ids": record_ids, "req_id": req_id},
        )
        counts[table] = r.rowcount or 0
    return counts


async def _soft_delete_full(db: AsyncSession, tenant_id, tenant_name, req_id) -> dict:
    """Critical #2 + #4: Schreibt deletion_request_id in alle Soft-Delete-Tabellen."""
    counts: dict = {}
    for table, stmt in _SOFT_DELETE_TABLES.items():
        r = await db.execute(
            text(stmt),
            {"tid": tenant_id, "req_id": req_id},
        )
        counts[table] = r.rowcount or 0
    await db.execute(
        text(
            "UPDATE tenants SET enabled = false, disabled_reason = :r, "
            "disabled_at = NOW(), disabled_by = 'rtbf_request' "
            "WHERE id = :tid"
        ),
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

    # req_id wird VOR den Soft-Deletes erzeugt, damit die FK-Spalten sofort
    # korrekt gesetzt werden (Critical #2).
    req_id = uuid.uuid4()

    affected: dict = {}
    if payload.mode == "full":
        affected = await _soft_delete_full(db, tenant.id, tenant.name, req_id)
    elif payload.mode == "memory_selective":
        n = await _soft_delete_memory(
            db, tenant.id, payload.older_than_days, payload.classification, req_id
        )
        affected = {"memory_chunks": n}
    elif payload.mode == "telegram_purge":
        affected = await _soft_delete_telegram(db, tenant.id, payload.older_than_days, req_id)
    elif payload.mode == "audit_selective":
        affected = await _soft_delete_audit(db, tenant.id, payload.record_ids or [], req_id)

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
            "id": req_id,
            "tid": tenant.id,
            "tname": tenant.name,
            "mode": payload.mode,
            "pf": json.dumps(
                {
                    "older_than_days": payload.older_than_days,
                    "classification": payload.classification,
                    "record_ids": payload.record_ids,
                }
            ),
            "aff": json.dumps(affected),
            "now": now,
            "ru": recovery_until,
            "notes": payload.notes,
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
    rows = (
        await db.execute(
            text("""
            SELECT id, mode, status, affected_records, requested_at,
                   recovery_until, soft_deleted_at, hard_deleted_at, recovered_at, notes
            FROM deletion_requests
            WHERE tenant_id = :tid
            ORDER BY requested_at DESC LIMIT 50
        """),
            {"tid": tenant.id},
        )
    ).fetchall()
    return {
        "history": [
            {
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
            }
            for r in rows
        ]
    }


@router.post("/me/data-deletion/{req_id}/recover")
async def recover_deletion(
    req_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            text("""
            SELECT id, mode, status, recovery_until, affected_records
            FROM deletion_requests
            WHERE id = :id AND tenant_id = :tid
        """),
            {"id": req_id, "tid": tenant.id},
        )
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="deletion request not found")
    if row.status != "soft_deleted":
        raise HTTPException(status_code=409, detail=f"cannot recover: status={row.status}")
    if row.recovery_until and row.recovery_until < datetime.datetime.now(datetime.UTC):
        raise HTTPException(status_code=410, detail="recovery period expired")

    affected: dict = row.affected_records or {}
    restored: dict = {}

    # M2: f-String-Loop durch statische Whitelist _RECOVER_TABLES ersetzt.
    # Critical #2: Recovery per deletion_request_id FK — kein ±2s Zeitfenster mehr.
    # Nur Rows die exakt zu diesem Request gehören werden zurückgeholt.
    # telegram_message_log ist ebenfalls in _RECOVER_TABLES (M5-Recovery-Symmetrie).
    for table, stmt in _RECOVER_TABLES.items():
        if affected.get(table, 0) > 0:
            r = await db.execute(
                text(stmt),
                {"tid": tenant.id, "req_id": req_id},
            )
            restored[table] = r.rowcount or 0

    if row.mode == "full":
        await db.execute(
            text(
                "UPDATE tenants SET enabled = true, disabled_reason = NULL, "
                "disabled_at = NULL, disabled_by = NULL WHERE id = :tid"
            ),
            {"tid": tenant.id},
        )

    await db.execute(
        text(
            "UPDATE deletion_requests SET status = 'recovered', recovered_at = NOW() WHERE id = :id"
        ),
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
    row = (
        await db.execute(
            text("""
            SELECT id, mode, status, affected_records, requested_at,
                   recovery_until, soft_deleted_at, hard_deleted_at, recovered_at, notes
            FROM deletion_requests
            WHERE id = :id AND tenant_id = :tid
        """),
            {"id": req_id, "tid": tenant.id},
        )
    ).fetchone()
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
