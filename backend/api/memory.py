"""Memory-API für Phase 5.4 (Issue #140) — Unternehmensgedächtnis.

Endpoints:
  GET  /api/memory/search   — semantische Suche im Tenant-Gedächtnis
  GET  /api/memory/recent   — neueste Chunks (auch ohne Embedding)
  GET  /api/memory/picker   — Vorschläge "Du hattest vor N Tagen über X gesprochen"
  GET  /api/memory/stats    — Counts pro source_type + classification
  POST /api/memory/note     — manuelle Notiz hinzufügen
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from services.anweisungs_marker import SQL_OHNE_ANWEISUNGEN
from services.embedding_service import (
    ALLOWED_CLASSIFICATIONS,
    ALLOWED_SOURCE_TYPES,
    search_similar,
    store_chunk,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/memory/search")
async def memory_search(
    q: str = Query(..., min_length=2, description="Suchanfrage"),
    limit: int = Query(10, ge=1, le=50),
    classification: str | None = Query(None),
    source_types: str | None = Query(
        None, description="Komma-separierte Liste, z.B. voice_telegram,manual_note"
    ),
    min_similarity: float = Query(0.0, ge=0.0, le=1.0),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Semantische Suche im Tenant-Gedächtnis via cosine-Distance."""
    if classification and classification not in ALLOWED_CLASSIFICATIONS:
        raise HTTPException(
            400, f"Unbekannte classification — erlaubt: {sorted(ALLOWED_CLASSIFICATIONS)}"
        )
    types_list = None
    if source_types:
        types_list = [s.strip() for s in source_types.split(",") if s.strip()]
        bad = [s for s in types_list if s not in ALLOWED_SOURCE_TYPES]
        if bad:
            raise HTTPException(400, f"Unbekannte source_types: {bad}")

    results = await search_similar(
        db,
        tenant_id=str(tenant.id),
        query_text=q,
        limit=limit,
        min_similarity=min_similarity,
        classification=classification,
        source_types=types_list,
        # Diese Route ist eine ANSICHT auf den Rohbestand, kein Erzeuger. Wer nachsehen
        # will, ob die Markierung sitzt, muss das Markierte auch sehen koennen.
        include_instructions=True,
    )
    return {"query": q, "count": len(results), "results": results}


@router.get("/memory/recent")
async def memory_recent(
    limit: int = Query(20, ge=1, le=100),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Neueste Chunks chronologisch — auch ohne Embedding."""
    rows = (
        await db.execute(
            text(
                "SELECT id, source_type, source_ref, content_text, classification, "
                "       metadata, created_at, "
                "       (embedding IS NOT NULL) AS has_embedding "
                "FROM memory_chunks "
                "WHERE tenant_id = :tid "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            {"tid": tenant.id, "lim": limit},
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "source_type": r.source_type,
            "source_ref": r.source_ref,
            "content_text": r.content_text,
            "classification": r.classification,
            "metadata": dict(r.metadata or {}),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "has_embedding": bool(r.has_embedding),
        }
        for r in rows
    ]


@router.get("/memory/picker")
async def memory_picker(
    days_min: int = Query(7, ge=1, le=365, description="Mindestalter in Tagen für 'vor … Tagen'"),
    days_max: int = Query(60, ge=1, le=365),
    limit: int = Query(5, ge=1, le=20),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Picker-Vorschläge: ältere Chunks die vergessen wurden.

    Sortiert by random + Alters-Boost: Chunks zwischen days_min und days_max,
    bevorzugt mit Klassifikation 'stories' (am Content-Wert hochwertigste).
    """
    if days_min >= days_max:
        raise HTTPException(400, "days_min muss < days_max sein")
    cutoff_min = datetime.utcnow() - timedelta(days=days_max)
    cutoff_max = datetime.utcnow() - timedelta(days=days_min)
    rows = (
        await db.execute(
            text(
                "SELECT id, source_type, content_text, classification, metadata, created_at "
                "FROM memory_chunks "
                "WHERE tenant_id = :tid "
                "  AND created_at BETWEEN :cmin AND :cmax "
                f"  AND {SQL_OHNE_ANWEISUNGEN} "
                "ORDER BY "
                "  CASE classification WHEN 'stories' THEN 0 WHEN 'werte' THEN 1 ELSE 2 END, "
                "  random() "
                "LIMIT :lim"
            ),
            {"tid": tenant.id, "cmin": cutoff_min, "cmax": cutoff_max, "lim": limit},
        )
    ).all()
    out = []
    for r in rows:
        days_ago = (datetime.utcnow() - r.created_at).days if r.created_at else None
        # erste 80 chars als Preview
        preview = (r.content_text or "")[:120]
        if len(r.content_text or "") > 120:
            preview += "…"
        out.append(
            {
                "id": str(r.id),
                "source_type": r.source_type,
                "preview": preview,
                "classification": r.classification,
                "days_ago": days_ago,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "suggestion": _suggestion_text(r.classification, days_ago),
            }
        )
    return {"count": len(out), "items": out}


def _suggestion_text(classification: str | None, days_ago: int | None) -> str:
    when = f"vor {days_ago} Tagen" if days_ago else "kürzlich"
    if classification == "stories":
        return f"Du hast {when} eine Geschichte erzählt — daraus wird ein guter Post."
    if classification == "werte":
        return f"Vor {when} hast du über deine Werte gesprochen — Material für Trust-Content."
    if classification == "konflikte":
        return f"Vor {when} hast du eine Spannung beschrieben — gut für ehrlichen Content."
    return f"Du hast {when} etwas notiert — willst du daraus einen Post machen?"


@router.get("/memory/stats")
async def memory_stats(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Counts pro source_type + classification + Embedding-Coverage."""
    total = (
        await db.execute(
            text("SELECT COUNT(*) AS c FROM memory_chunks WHERE tenant_id = :tid"),
            {"tid": tenant.id},
        )
    ).scalar() or 0
    embedded = (
        await db.execute(
            text(
                "SELECT COUNT(*) AS c FROM memory_chunks "
                "WHERE tenant_id = :tid AND embedding IS NOT NULL"
            ),
            {"tid": tenant.id},
        )
    ).scalar() or 0
    by_source = (
        await db.execute(
            text(
                "SELECT source_type, COUNT(*) AS c FROM memory_chunks "
                "WHERE tenant_id = :tid GROUP BY source_type ORDER BY c DESC"
            ),
            {"tid": tenant.id},
        )
    ).all()
    by_class = (
        await db.execute(
            text(
                "SELECT COALESCE(classification, 'unklassifiziert') AS c, COUNT(*) AS n "
                "FROM memory_chunks WHERE tenant_id = :tid "
                "GROUP BY classification ORDER BY n DESC"
            ),
            {"tid": tenant.id},
        )
    ).all()
    return {
        "total": int(total),
        "embedded": int(embedded),
        "embedding_coverage": round(embedded / total, 3) if total else 0,
        "by_source": [{"source_type": r.source_type, "count": int(r.c)} for r in by_source],
        "by_classification": [{"classification": r.c, "count": int(r.n)} for r in by_class],
    }


class NoteIn(BaseModel):
    text: str
    classify: bool = True


@router.post("/memory/note")
async def add_manual_note(
    payload: NoteIn,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Manuelle Notiz hinzufügen (z.B. via UI)."""
    if not payload.text or not payload.text.strip():
        raise HTTPException(400, "text leer")
    chunk_id = await store_chunk(
        db=db,
        tenant_id=str(tenant.id),
        source_type="manual_note",
        content_text=payload.text.strip(),
        source_ref=None,
        metadata={"channel": "web"},
        classify=payload.classify,
    )
    return {"id": chunk_id, "status": "ok"}
