"""Embedding-Service für Phase 5 (Issue #140) — Unternehmensgedächtnis.

Erzeugt 768-dim Embeddings via Requesty.ai-Router (model
`vertex/text-embedding-004` EU-Region) und persistiert sie in der
`memory_chunks`-Tabelle.

Plus: leichter Klassifikator (werte/stories/konflikte) via
LLMService.complete_json mit kleinem JSON-Schema.

Designentscheidungen:
- Embedding über Requesty (gleicher Auth-Pfad wie LLMService) —
  kein direkter Vertex-SDK-Setup nötig.
- Bei Embedding-Fehler: Chunk wird OHNE embedding gespeichert
  (HNSW-Index ist PARTIAL `WHERE embedding IS NOT NULL`); kann
  später nachträglich embeddet werden.
- Klassifikator ist optional; bei Drift/Fehler: classification=NULL.
- Tenant-Isolation: Service-Methoden nehmen tenant_id zwingend.
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Sequence

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.llm import llm_service

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768
EMBEDDING_MODEL = "vertex/text-embedding-004"  # Requesty-Routing, EU-Region

ALLOWED_SOURCE_TYPES = {
    "voice_telegram",
    "voice_whatsapp",
    "photo_telegram",
    "photo_whatsapp",
    "manual_note",
    "transcript_extra",
}
ALLOWED_CLASSIFICATIONS = {"werte", "stories", "konflikte"}


class EmbeddingError(Exception):
    """Wrapper für Embedding-Provider-Fehler."""


async def embed_text(text_input: str, *, timeout: float = 15.0) -> Optional[list[float]]:
    """Erzeuge ein 768-dim Embedding für `text_input` via Requesty.

    Returns None bei Fehler (caller persistiert Chunk dann ohne embedding).
    Wirft KEINE Exception — soll nicht den Caller-Pfad blockieren.
    """
    base_url = (settings.litellm_base_url or "").rstrip("/")
    api_key = settings.litellm_api_key or ""
    if not base_url or not api_key:
        logger.warning("Embedding: kein litellm_base_url/api_key konfiguriert — skippe")
        return None
    if not text_input or not text_input.strip():
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": EMBEDDING_MODEL, "input": text_input[:8000]}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base_url}/embeddings", json=payload, headers=headers)
        if resp.status_code != 200:
            logger.warning(
                "Embedding %s → HTTP %s: %s",
                EMBEDDING_MODEL,
                resp.status_code,
                resp.text[:200],
            )
            return None
        data = resp.json()
        items = data.get("data") or []
        if not items:
            logger.warning("Embedding-Response ohne data: %s", str(data)[:200])
            return None
        emb = items[0].get("embedding")
        if not isinstance(emb, list) or len(emb) != EMBEDDING_DIM:
            logger.warning(
                "Embedding-Response Dimension unerwartet: %s (erwartet %d)",
                len(emb) if isinstance(emb, list) else type(emb).__name__,
                EMBEDDING_DIM,
            )
            return None
        return [float(x) for x in emb]
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning("Embedding-Network-Error: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 — defensive
        logger.warning("Embedding-Unknown-Error: %s", exc)
        return None


async def classify_chunk(content: str) -> Optional[str]:
    """Klassifiziert einen Chunk in werte/stories/konflikte via LLM.

    Returns None wenn Drift, Fehler oder zu wenig Inhalt.
    """
    if not content or len(content.strip()) < 20:
        return None
    system_prompt = (
        "Klassifiziere den folgenden Text in genau EINE der drei Kategorien:\n"
        "- 'werte' — Werte, Überzeugungen, Prinzipien, das was dem Unternehmer wichtig ist\n"
        "- 'stories' — Geschichten, Anekdoten, konkrete Vorher-Nachher-Erlebnisse\n"
        "- 'konflikte' — Spannungen, Reibung, Probleme, was nicht klappt\n\n"
        "Antworte AUSSCHLIESSLICH mit JSON: {\"classification\": \"werte\"|\"stories\"|\"konflikte\"}"
    )
    try:
        result = await llm_service.complete_json(
            prompt=content[:2000],
            system=system_prompt,
            model="gemini-flash",
            purpose="tagging",
        )
        if isinstance(result, dict):
            cls = (result.get("classification") or "").strip().lower()
            if cls in ALLOWED_CLASSIFICATIONS:
                return cls
        return None
    except Exception as exc:  # noqa: BLE001
        logger.info("Classify skipped: %s", exc)
        return None


def _embedding_to_pg(values: Sequence[float]) -> str:
    """pgvector-Literal-Format: '[v1,v2,...]'."""
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


async def store_chunk(
    db: AsyncSession,
    *,
    tenant_id: str,
    source_type: str,
    content_text: str,
    source_ref: Optional[str] = None,
    metadata: Optional[dict] = None,
    classify: bool = True,
) -> str:
    """Persistiert einen Chunk mit Embedding + (optional) Klassifikation.

    Returns die ID des angelegten memory_chunks-Eintrags.
    """
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError(f"Unbekannter source_type: {source_type}")
    if not content_text or not content_text.strip():
        raise ValueError("content_text leer")

    embedding = await embed_text(content_text)
    classification = await classify_chunk(content_text) if classify else None

    params = {
        "tenant_id": tenant_id,
        "source_type": source_type,
        "source_ref": source_ref,
        "content_text": content_text,
        "classification": classification,
        "metadata": json.dumps(metadata or {}, ensure_ascii=False),
    }
    if embedding is not None:
        params["embedding_str"] = _embedding_to_pg(embedding)
        sql = text(
            "INSERT INTO memory_chunks "
            "(tenant_id, source_type, source_ref, content_text, classification, metadata, embedding) "
            "VALUES (CAST(:tenant_id AS uuid), :source_type, :source_ref, :content_text, :classification, "
            "        CAST(:metadata AS jsonb), CAST(:embedding_str AS vector)) "
            "RETURNING id"
        )
    else:
        sql = text(
            "INSERT INTO memory_chunks "
            "(tenant_id, source_type, source_ref, content_text, classification, metadata) "
            "VALUES (CAST(:tenant_id AS uuid), :source_type, :source_ref, :content_text, :classification, "
            "        CAST(:metadata AS jsonb)) "
            "RETURNING id"
        )

    row = (await db.execute(sql, params)).fetchone()
    await db.commit()
    new_id = str(row.id)
    logger.info(
        "memory_chunk angelegt id=%s tenant=%s type=%s embed=%s class=%s",
        new_id,
        tenant_id,
        source_type,
        bool(embedding),
        classification,
    )
    return new_id


async def search_similar(
    db: AsyncSession,
    *,
    tenant_id: str,
    query_text: str,
    limit: int = 10,
    min_similarity: float = 0.0,
    classification: Optional[str] = None,
    source_types: Optional[Sequence[str]] = None,
) -> list[dict]:
    """Semantische Suche im Tenant-Gedächtnis via cosine-Distance."""
    query_emb = await embed_text(query_text)
    if query_emb is None:
        return []

    where_extra = ["embedding IS NOT NULL", "tenant_id = CAST(:tid AS uuid)"]
    params = {
        "tid": tenant_id,
        "qemb": _embedding_to_pg(query_emb),
        "limit": limit,
    }
    if classification and classification in ALLOWED_CLASSIFICATIONS:
        where_extra.append("classification = :class")
        params["class"] = classification
    if source_types:
        params["src_list"] = list(source_types)
        where_extra.append("source_type = ANY(:src_list)")

    where_sql = " AND ".join(where_extra)
    sql = text(
        f"SELECT id, source_type, source_ref, content_text, classification, metadata, "
        f"       created_at, "
        f"       1 - (embedding <=> CAST(:qemb AS vector)) AS similarity "
        f"FROM memory_chunks "
        f"WHERE {where_sql} "
        f"ORDER BY embedding <=> CAST(:qemb AS vector) "
        f"LIMIT :limit"
    )
    rows = (await db.execute(sql, params)).fetchall()
    out = []
    for r in rows:
        sim = float(r.similarity or 0)
        if sim < min_similarity:
            continue
        out.append({
            "id": str(r.id),
            "source_type": r.source_type,
            "source_ref": r.source_ref,
            "content_text": r.content_text,
            "classification": r.classification,
            "metadata": dict(r.metadata or {}),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "similarity": sim,
        })
    return out
