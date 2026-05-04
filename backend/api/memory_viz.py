"""Vector-DB-Visualisierung (Issue #148, Welle F).

Liefert nodes + edges für force-directed-Graph.
Cosine-Similarity wird via pgvector im Server berechnet (kein UMAP nötig
bei kleinen Datasets <500 Chunks). Frontend (react-force-graph-2d) macht
den Layout via d3-force.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant

logger = logging.getLogger(__name__)
router = APIRouter()


CLASSIFICATION_COLORS = {
    "werte": "#2563eb",
    "stories": "#16a34a",
    "konflikte": "#dc2626",
    None: "#6b7280",
}

SOURCE_TYPE_GROUPS = {
    "voice_telegram": "voice",
    "voice_whatsapp": "voice",
    "photo_telegram": "photo",
    "photo_whatsapp": "photo",
    "manual_note": "manual",
}


@router.get("/memory/viz-data")
async def get_viz_data(
    days: int = Query(180, ge=1, le=3650, description="Zeitfenster in Tagen"),
    classification: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    edge_threshold: float = Query(0.75, ge=0.5, le=1.0,
                                   description="Cosine-Similarity-Schwellwert für Edges"),
    max_edges: int = Query(150, ge=10, le=1000),
    max_nodes: int = Query(200, ge=10, le=1000),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    where = ["tenant_id = :tid", "embedding IS NOT NULL", "deleted_at IS NULL",
             "created_at >= NOW() - make_interval(days => :days)"]
    params: dict = {"tid": tenant.id, "days": days, "max_nodes": max_nodes}
    if classification:
        where.append("classification = :cls")
        params["cls"] = classification
    if source_type:
        where.append("source_type = :st")
        params["st"] = source_type

    where_sql = " AND ".join(where)
    rows = (await db.execute(
        text(f"""
            SELECT id, content_text, classification, source_type,
                   created_at, source_ref
            FROM memory_chunks
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT :max_nodes
        """),
        params,
    )).fetchall()

    nodes = []
    node_ids = []
    for r in rows:
        node_ids.append(str(r.id))
        nodes.append({
            "id": str(r.id),
            "label": (r.content_text or "")[:80] + ("…" if len(r.content_text or "") > 80 else ""),
            "full_text": r.content_text,
            "classification": r.classification,
            "source_type": r.source_type,
            "source_group": SOURCE_TYPE_GROUPS.get(r.source_type, "other"),
            "color": CLASSIFICATION_COLORS.get(r.classification) or CLASSIFICATION_COLORS[None],
            "size": 6 if r.classification else 4,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    if len(node_ids) < 2:
        edges = []
    else:
        params2: dict = {"tid": tenant.id, "thresh": edge_threshold,
                         "max_edges": max_edges, "ids": node_ids}
        edge_rows = (await db.execute(
            text("""
                SELECT a.id AS src, b.id AS dst,
                       1 - (a.embedding <=> b.embedding) AS sim
                FROM memory_chunks a
                JOIN memory_chunks b
                  ON a.tenant_id = b.tenant_id
                 AND a.id < b.id
                WHERE a.tenant_id = :tid
                  AND a.id = ANY(:ids)
                  AND b.id = ANY(:ids)
                  AND a.embedding IS NOT NULL
                  AND b.embedding IS NOT NULL
                  AND 1 - (a.embedding <=> b.embedding) >= :thresh
                ORDER BY sim DESC
                LIMIT :max_edges
            """),
            params2,
        )).fetchall()
        edges = [{
            "source": str(e.src),
            "target": str(e.dst),
            "weight": float(e.sim),
        } for e in edge_rows]

    stats_rows = (await db.execute(
        text("""
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS with_embedding,
              COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) AS soft_deleted,
              COUNT(DISTINCT classification) FILTER (WHERE classification IS NOT NULL) AS classes,
              MIN(created_at) AS earliest,
              MAX(created_at) AS latest
            FROM memory_chunks
            WHERE tenant_id = :tid
        """),
        {"tid": tenant.id},
    )).fetchone()

    by_class = (await db.execute(
        text("""
            SELECT classification, COUNT(*) AS n
            FROM memory_chunks
            WHERE tenant_id = :tid AND deleted_at IS NULL
            GROUP BY classification ORDER BY n DESC
        """),
        {"tid": tenant.id},
    )).fetchall()
    by_source = (await db.execute(
        text("""
            SELECT source_type, COUNT(*) AS n
            FROM memory_chunks
            WHERE tenant_id = :tid AND deleted_at IS NULL
            GROUP BY source_type ORDER BY n DESC
        """),
        {"tid": tenant.id},
    )).fetchall()

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "total": stats_rows.total,
            "with_embedding": stats_rows.with_embedding,
            "soft_deleted": stats_rows.soft_deleted,
            "shown_nodes": len(nodes),
            "shown_edges": len(edges),
            "earliest": stats_rows.earliest.isoformat() if stats_rows.earliest else None,
            "latest": stats_rows.latest.isoformat() if stats_rows.latest else None,
            "by_classification": [{"name": r.classification or "unklassifiziert", "count": r.n} for r in by_class],
            "by_source_type": [{"name": r.source_type, "count": r.n} for r in by_source],
        },
        "filters": {
            "days": days,
            "classification": classification,
            "source_type": source_type,
            "edge_threshold": edge_threshold,
        },
    }
