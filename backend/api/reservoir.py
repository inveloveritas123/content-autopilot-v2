"""Reservoir API — Ingest source texts for quote validation."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from services.quote_extractor import extract_quotes

router = APIRouter(prefix="/reservoir", tags=["reservoir"])


class ReservoirIngestRequest(BaseModel):
    source_type: str  # 'transcript', 'article', 'voice_profile'
    source_ref: Optional[str] = None
    content_text: str


@router.post("/ingest")
async def ingest_source(
    req: ReservoirIngestRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a source text into the tenant's reservoir and extract quotes."""
    if not req.content_text.strip():
        raise HTTPException(400, "content_text darf nicht leer sein")

    quotes = extract_quotes(req.content_text)

    entry_id = str(uuid.uuid4())
    # PostgreSQL TEXT[] requires json cast for safe binding of lists via text()
    import json as _json
    await db.execute(
        text("""
            INSERT INTO tenant_reservoir (id, tenant_id, source_type, source_ref, content_text, extracted_quotes)
            VALUES (:id, :tid, :stype, :sref, :ctext,
                    ARRAY(SELECT * FROM json_array_elements_text(CAST(:quotes AS json))))
        """),
        {
            "id": entry_id,
            "tid": str(tenant.id),
            "stype": req.source_type[:50],
            "sref": (req.source_ref or "")[:500],
            "ctext": req.content_text,
            "quotes": _json.dumps(quotes),
        }
    )
    await db.commit()
    return {
        "id": entry_id,
        "source_type": req.source_type,
        "extracted_quote_count": len(quotes),
        "extracted_quotes": quotes[:10],  # preview
    }


@router.get("/")
async def list_reservoir(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List reservoir entries for this tenant."""
    rows = await db.execute(
        text("""SELECT id, source_type, source_ref, array_length(extracted_quotes, 1) as quote_count, created_at
                FROM tenant_reservoir WHERE tenant_id = :tid ORDER BY created_at DESC"""),
        {"tid": str(tenant.id)}
    )
    return {"entries": [dict(r._mapping) for r in rows.fetchall()]}


@router.delete("/{entry_id}")
async def delete_reservoir_entry(
    entry_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete a reservoir entry."""
    result = await db.execute(
        text("DELETE FROM tenant_reservoir WHERE id = :id AND tenant_id = :tid"),
        {"id": entry_id, "tid": str(tenant.id)}
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Reservoir-Eintrag nicht gefunden")
    return {"status": "deleted"}
