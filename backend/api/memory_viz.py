"""Vector-DB-Visualisierung (Issue #148, Welle F).

Liefert nodes + edges für force-directed-Graph.
Cosine-Similarity wird via pgvector im Server berechnet (kein UMAP nötig
bei kleinen Datasets <500 Chunks). Frontend (react-force-graph-2d) macht
den Layout via d3-force.

Critical #3 — PII-Leak-Fix:
- Default-Response liefert nur `text_preview` (max 200 Zeichen), kein `full_text`.
- Neuer Detail-Endpoint `GET /api/memory/viz-data/{chunk_id}/full` erfordert
  Confirm-Token (POST body `{"confirm": true, "reason": "..."}`) und loggt
  den Zugriff in llm_call_logs als Tenant-Audit (task_type='memory_full_view').
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant

logger = logging.getLogger(__name__)
router = APIRouter()

_TEXT_PREVIEW_MAX = 200


def _make_preview(content: str | None) -> str:
    if not content:
        return ""
    if len(content) <= _TEXT_PREVIEW_MAX:
        return content
    return content[:_TEXT_PREVIEW_MAX] + " …"


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
    classification: str | None = Query(None),
    source_type: str | None = Query(None),
    edge_threshold: float = Query(
        0.75, ge=0.5, le=1.0, description="Cosine-Similarity-Schwellwert für Edges"
    ),
    max_edges: int = Query(150, ge=10, le=1000),
    max_nodes: int = Query(200, ge=10, le=1000),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    # S1: Whitelist-Check vor Query-Building — verhindert unerwartete Werte
    # auch wenn die Werte parametrisiert sind (Defense-in-Depth, konsistent mit PR-Ziel).
    _ALLOWED_CLASSIFICATIONS = set(CLASSIFICATION_COLORS.keys()) - {None}
    _ALLOWED_SOURCE_TYPES = set(SOURCE_TYPE_GROUPS.keys())
    if classification and classification not in _ALLOWED_CLASSIFICATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"classification muss einer von {sorted(_ALLOWED_CLASSIFICATIONS)} sein",
        )
    if source_type and source_type not in _ALLOWED_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"source_type muss einer von {sorted(_ALLOWED_SOURCE_TYPES)} sein",
        )

    where = [
        "tenant_id = :tid",
        "embedding IS NOT NULL",
        "deleted_at IS NULL",
        "created_at >= NOW() - make_interval(days => :days)",
    ]
    params: dict = {"tid": tenant.id, "days": days, "max_nodes": max_nodes}
    if classification:
        where.append("classification = :cls")
        params["cls"] = classification
    if source_type:
        where.append("source_type = :st")
        params["st"] = source_type

    where_sql = " AND ".join(where)
    rows = (
        await db.execute(
            text(f"""
            SELECT id, content_text, classification, source_type,
                   created_at, source_ref
            FROM memory_chunks
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT :max_nodes
        """),
            params,
        )
    ).fetchall()

    nodes = []
    node_ids = []
    for r in rows:
        node_ids.append(str(r.id))
        nodes.append(
            {
                "id": str(r.id),
                "label": (r.content_text or "")[:80]
                + ("…" if len(r.content_text or "") > 80 else ""),
                # Critical #3: Nur text_preview, kein full_text im Default-Response
                "text_preview": _make_preview(r.content_text),
                "classification": r.classification,
                "source_type": r.source_type,
                "source_group": SOURCE_TYPE_GROUPS.get(r.source_type, "other"),
                "color": CLASSIFICATION_COLORS.get(r.classification) or CLASSIFICATION_COLORS[None],
                "size": 6 if r.classification else 4,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )

    if len(node_ids) < 2:
        edges = []
    else:
        params2: dict = {
            "tid": tenant.id,
            "thresh": edge_threshold,
            "max_edges": max_edges,
            "ids": node_ids,
        }
        edge_rows = (
            await db.execute(
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
            )
        ).fetchall()
        edges = [
            {
                "source": str(e.src),
                "target": str(e.dst),
                "weight": float(e.sim),
            }
            for e in edge_rows
        ]

    stats_rows = (
        await db.execute(
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
        )
    ).fetchone()

    by_class = (
        await db.execute(
            text("""
            SELECT classification, COUNT(*) AS n
            FROM memory_chunks
            WHERE tenant_id = :tid AND deleted_at IS NULL
            GROUP BY classification ORDER BY n DESC
        """),
            {"tid": tenant.id},
        )
    ).fetchall()
    by_source = (
        await db.execute(
            text("""
            SELECT source_type, COUNT(*) AS n
            FROM memory_chunks
            WHERE tenant_id = :tid AND deleted_at IS NULL
            GROUP BY source_type ORDER BY n DESC
        """),
            {"tid": tenant.id},
        )
    ).fetchall()

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
            "by_classification": [
                {"name": r.classification or "unklassifiziert", "count": r.n} for r in by_class
            ],
            "by_source_type": [{"name": r.source_type, "count": r.n} for r in by_source],
        },
        "filters": {
            "days": days,
            "classification": classification,
            "source_type": source_type,
            "edge_threshold": edge_threshold,
        },
    }


class FullTextConfirm(BaseModel):
    confirm: bool = Field(..., description="Muss true sein")
    reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Begründung für den Volltext-Abruf (Audit-Pflicht)",
    )


@router.post("/memory/viz-data/{chunk_id}/full")
async def get_chunk_full_text(
    chunk_id: str,
    body: FullTextConfirm,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Critical #3: Liefert den Volltext eines Memory-Chunks nach explizitem Confirm.

    - Erfordert `{"confirm": true, "reason": "..."}` im Request-Body.
    - Schreibt Audit-Eintrag in llm_call_logs (task_type='memory_full_view').
    - Gibt den vollen content_text zurück.
    """
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="confirm muss true sein — Zugriff wird im Audit-Log vermerkt.",
        )

    # Chunk laden — Tenant-Isolation sicherstellen
    row = (
        await db.execute(
            text("""
            SELECT id, content_text, classification, source_type, created_at
            FROM memory_chunks
            WHERE id = :cid AND tenant_id = :tid AND deleted_at IS NULL
        """),
            {"cid": chunk_id, "tid": tenant.id},
        )
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="chunk not found")

    # Audit-Log in llm_call_logs (kein LLM-Call, aber Zugriff auf PII)
    await db.execute(
        text("""
            INSERT INTO llm_call_logs
                (id, tenant_id, task_type, model, prompt_tokens, completion_tokens,
                 cost_cents, duration_ms, success, error_message, created_at)
            VALUES
                (:id, :tid, 'memory_full_view', 'none', 0, 0, 0, 0, true,
                 :reason, NOW())
        """),
        {
            "id": uuid.uuid4(),
            "tid": tenant.id,
            # M4: error_message wird bewusst als Audit-Feld missbraucht, weil
            # llm_call_logs kein dediziertes Freitext-Feld hat. JSON-Wrap macht
            # den Missbrauch explizit erkennbar.
            # TODO: dedizierte audit_notes-Spalte in llm_call_logs (Issue-Followup)
            "reason": json.dumps({"chunk_id": chunk_id, "reason": body.reason[:200]}),
        },
    )
    await db.commit()

    return {
        "id": str(row.id),
        "full_text": row.content_text,
        "classification": row.classification,
        "source_type": row.source_type,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "audit_logged": True,
    }
