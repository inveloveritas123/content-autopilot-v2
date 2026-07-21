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

Issue #150: Embedding-Versionierung.
- EMBEDDING_MODELS Registry — erweiterbar ohne Code-Änderung im Caller.
- embed() gibt immer (vector, model_id) zurück — Caller MUSS model_id
  mit-persistieren.
- ACTIVE_EMBEDDING_MODEL steuert Default; Canary-Tasks können abweichendes
  model_id übergeben.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.llm import llm_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedding-Modell-Registry (Issue #150)
# ---------------------------------------------------------------------------

EMBEDDING_MODELS: dict[str, dict] = {
    "gemini-embedding-001-1536d": {
        "provider": "requesty",  # geroutet via Requesty wie bisheriges Modell
        "model_name": "openai/text-embedding-3-small",  # Requesty-Alias (768-dim erzwungen via dim param)
        "dim": 1536,
        "active": True,
    },
}

ACTIVE_EMBEDDING_MODEL = "gemini-embedding-001-1536d"

# Legacy-Konstanten — bleiben für Rückwärtskompatibilität (bestehende Callers)
EMBEDDING_DIM = 1536
EMBEDDING_MODEL = EMBEDDING_MODELS[ACTIVE_EMBEDDING_MODEL]["model_name"]

ALLOWED_SOURCE_TYPES = {
    "voice_telegram",
    "voice_whatsapp",
    "voice_note",
    "photo_telegram",
    "photo_whatsapp",
    "photo_ocr",
    "manual_note",
    "manual_idea",
    "transcript_extra",
    "yt_transcript",
}
ALLOWED_CLASSIFICATIONS = {"werte", "stories", "konflikte"}


class EmbeddingError(Exception):
    """Wrapper für Embedding-Provider-Fehler."""


async def embed(
    text_input: str,
    model_id: str | None = None,
    *,
    timeout: float = 15.0,
) -> tuple[list[float] | None, str]:
    """Versioniertes Embedding — gibt immer (vector_or_None, model_id) zurück.

    Caller MUSS den zurückgegebenen model_id mit-persistieren (Issue #150).

    Args:
        text_input: Zu embettender Text.
        model_id:   Optionales Modell-Overrride (z.B. für Canary-Tasks).
                    Default: ACTIVE_EMBEDDING_MODEL.
        timeout:    HTTP-Timeout in Sekunden.

    Returns:
        Tuple (embedding_list_or_None, resolved_model_id).
    """
    resolved_model_id = model_id or ACTIVE_EMBEDDING_MODEL
    if resolved_model_id not in EMBEDDING_MODELS:
        logger.warning("embed: unbekanntes model_id=%s — nutze ACTIVE", resolved_model_id)
        resolved_model_id = ACTIVE_EMBEDDING_MODEL

    config = EMBEDDING_MODELS[resolved_model_id]
    model_name = config["model_name"]
    expected_dim = config["dim"]

    if not text_input or not text_input.strip():
        return None, resolved_model_id

    base_url = (settings.litellm_base_url or "").rstrip("/")
    api_key = settings.litellm_api_key or ""
    if not base_url or not api_key:
        logger.warning("embed: kein litellm_base_url/api_key konfiguriert — skippe")
        return None, resolved_model_id

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model_name, "input": text_input[:8000]}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base_url}/embeddings", json=payload, headers=headers)
        if resp.status_code != 200:
            logger.warning(
                "embed %s → HTTP %s: %s",
                model_name,
                resp.status_code,
                resp.text[:200],
            )
            return None, resolved_model_id
        data = resp.json()
        items = data.get("data") or []
        if not items:
            logger.warning("embed: Response ohne data: %s", str(data)[:200])
            return None, resolved_model_id
        emb = items[0].get("embedding")
        if not isinstance(emb, list) or len(emb) != expected_dim:
            logger.warning(
                "embed: Dimension unerwartet: %s (erwartet %d für %s)",
                len(emb) if isinstance(emb, list) else type(emb).__name__,
                expected_dim,
                resolved_model_id,
            )
            return None, resolved_model_id
        return [float(x) for x in emb], resolved_model_id
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning("embed: Network-Error: %s", exc)
        return None, resolved_model_id
    except Exception as exc:
        logger.warning("embed: Unknown-Error: %s", exc)
        return None, resolved_model_id


async def embed_text(text_input: str, *, timeout: float = 15.0) -> list[float] | None:
    """Legacy-Wrapper — gibt nur den Vektor zurück (ohne model_id).

    Für neuen Code: embed() verwenden, das model_id mit zurückgibt.
    """
    vector, _ = await embed(text_input, timeout=timeout)
    return vector


async def classify_chunk(content: str) -> str | None:
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
        'Antworte AUSSCHLIESSLICH mit JSON: {"classification": "werte"|"stories"|"konflikte"}'
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
    except Exception as exc:
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
    source_ref: str | None = None,
    metadata: dict | None = None,
    classify: bool = True,
) -> str:
    """Persistiert einen Chunk mit Embedding + (optional) Klassifikation.

    Returns die ID des angelegten memory_chunks-Eintrags.
    """
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError(f"Unbekannter source_type: {source_type}")
    if not content_text or not content_text.strip():
        raise ValueError("content_text leer")

    # Issue #150: embed() gibt (vector, model_id) zurück — model_id persistieren
    embedding, used_model_id = await embed(content_text)
    classification = await classify_chunk(content_text) if classify else None

    params = {
        "tenant_id": tenant_id,
        "source_type": source_type,
        "source_ref": source_ref,
        "content_text": content_text,
        "classification": classification,
        "metadata": json.dumps(metadata or {}, ensure_ascii=False),
        "embedding_model_id": used_model_id,
    }
    if embedding is not None:
        params["embedding_str"] = _embedding_to_pg(embedding)
        sql = text(
            "INSERT INTO memory_chunks "
            "(tenant_id, source_type, source_ref, content_text, classification, metadata, "
            " embedding, embedding_model_id) "
            "VALUES (CAST(:tenant_id AS uuid), :source_type, :source_ref, :content_text, :classification, "
            "        CAST(:metadata AS jsonb), CAST(:embedding_str AS vector), :embedding_model_id) "
            "RETURNING id"
        )
    else:
        sql = text(
            "INSERT INTO memory_chunks "
            "(tenant_id, source_type, source_ref, content_text, classification, metadata, embedding_model_id) "
            "VALUES (CAST(:tenant_id AS uuid), :source_type, :source_ref, :content_text, :classification, "
            "        CAST(:metadata AS jsonb), :embedding_model_id) "
            "RETURNING id"
        )

    row = (await db.execute(sql, params)).fetchone()
    await db.commit()
    new_id = str(row.id)
    logger.info(
        "memory_chunk angelegt id=%s tenant=%s type=%s embed=%s class=%s model=%s",
        new_id,
        tenant_id,
        source_type,
        bool(embedding),
        classification,
        used_model_id,
    )
    return new_id


async def store_chunks_multi(
    db: AsyncSession,
    *,
    tenant_id: str,
    source_type: str,
    chunks: list,  # list[chunker.Chunk] — lazy import um Zirkel zu vermeiden
    source_ref: str | None = None,
    base_metadata: dict | None = None,
    classify: bool = True,
) -> list[str]:
    """Persistiert mehrere Chunks (aus chunker.chunk_text) mit prev/next-Links.

    Workflow:
    1. Alle Chunks speichern (ohne prev/next-IDs, da noch unbekannt).
    2. chunker.link_chunks_with_ids() aufrufen → IDs in Chunk-Objekten setzen.
    3. Alle Chunks mit UPDATE auf prev/next patchen.

    Returns: Liste der angelegten memory_chunk-IDs in Chunk-Reihenfolge.

    Falls nur 1 Chunk: store_chunk() direkt nutzen (kein UPDATE noetig).
    """
    from services.chunker import link_chunks_with_ids  # lazy import

    if not chunks:
        return []

    if len(chunks) == 1:
        chunk_meta = dict(base_metadata or {})
        chunk_meta["chunk_position"] = 0
        chunk_meta["chunk_total"] = 1
        chunk_id = await store_chunk(
            db,
            tenant_id=tenant_id,
            source_type=source_type,
            content_text=chunks[0].text,
            source_ref=source_ref,
            metadata=chunk_meta,
            classify=classify,
        )
        return [chunk_id]

    # Schritt 1: Alle Chunks speichern (ohne prev/next)
    db_ids: list[str] = []
    for i, chunk in enumerate(chunks):
        chunk_meta = dict(base_metadata or {})
        chunk_meta["chunk_position"] = i
        chunk_meta["chunk_total"] = len(chunks)
        chunk_id = await store_chunk(
            db,
            tenant_id=tenant_id,
            source_type=source_type,
            content_text=chunk.text,
            source_ref=source_ref,
            metadata=chunk_meta,
            classify=classify,
        )
        db_ids.append(chunk_id)

    # Schritt 2: IDs in Chunk-Objekten setzen
    link_chunks_with_ids(chunks, db_ids)

    # Schritt 3: prev/next-IDs via UPDATE eintragen
    for chunk, chunk_id in zip(chunks, db_ids, strict=False):
        prev_id = chunk.prev_chunk_id
        next_id = chunk.next_chunk_id
        if prev_id is None and next_id is None:
            continue  # Single-Chunk-Fall — kein Update noetig
        update_sql = text(
            "UPDATE memory_chunks "
            "SET metadata = metadata || CAST(:patch AS jsonb) "
            "WHERE id = CAST(:cid AS uuid)"
        )
        patch: dict = {}
        if prev_id is not None:
            patch["prev_chunk_id"] = prev_id
        if next_id is not None:
            patch["next_chunk_id"] = next_id
        await db.execute(
            update_sql,
            {
                "patch": json.dumps(patch),
                "cid": chunk_id,
            },
        )

    await db.commit()
    logger.info(
        "store_chunks_multi: %d chunks gespeichert, tenant=%s type=%s",
        len(db_ids),
        tenant_id,
        source_type,
    )
    return db_ids


async def search_similar(
    db: AsyncSession,
    *,
    tenant_id: str,
    query_text: str,
    limit: int = 10,
    min_similarity: float = 0.0,
    classification: str | None = None,
    source_types: Sequence[str] | None = None,
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
        out.append(
            {
                "id": str(r.id),
                "source_type": r.source_type,
                "source_ref": r.source_ref,
                "content_text": r.content_text,
                "classification": r.classification,
                "metadata": dict(r.metadata or {}),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "similarity": sim,
            }
        )
    return out


async def _lexical_search(
    db: AsyncSession,
    *,
    tenant_id: str,
    query_text: str,
    limit: int,
    classification: str | None = None,
    source_types: Sequence[str] | None = None,
) -> list[dict]:
    """Lexikalischer Zweig (tsvector/ts_rank_cd) für Hybrid-Retrieval.

    Portiert aus LunaDeva knowledge_service._lexical_candidates. Fängt fehlende
    ``content_tsv``-Spalte (alte DB ohne Migration 060) defensiv ab und gibt
    dann leer zurück — der Aufrufer (search_reranked) fällt in diesem Fall auf
    reines Vektor-Retrieval zurück ("Hybrid schlägt Purismus", aber niemals
    blockierend).
    """
    where_extra = ["content_tsv @@ websearch_to_tsquery('german', :q)", "tenant_id = CAST(:tid AS uuid)"]
    params: dict = {"tid": tenant_id, "q": query_text, "limit": limit}
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
        f"       ts_rank_cd(content_tsv, websearch_to_tsquery('german', :q)) AS lex_rank "
        f"FROM memory_chunks "
        f"WHERE {where_sql} "
        f"ORDER BY lex_rank DESC "
        f"LIMIT :limit"
    )
    try:
        rows = (await db.execute(sql, params)).fetchall()
    except Exception as exc:
        logger.warning(
            "search_reranked: lexikalischer Zweig übersprungen (content_tsv evtl. fehlend): %s",
            exc,
        )
        return []
    out = []
    for r in rows:
        out.append(
            {
                "id": str(r.id),
                "source_type": r.source_type,
                "source_ref": r.source_ref,
                "content_text": r.content_text,
                "classification": r.classification,
                "metadata": dict(r.metadata or {}),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "similarity": 0.0,
            }
        )
    return out


async def search_reranked(
    db: AsyncSession,
    *,
    tenant_id: str,
    query_text: str,
    limit: int = 10,
    min_similarity: float = 0.0,
    classification: str | None = None,
    source_types: Sequence[str] | None = None,
    over_fetch: int = 20,
    use_hybrid: bool = True,
    use_rerank: bool = True,
) -> list[dict]:
    """Hybrid-Search (Vektor + Lexical, RRF-fusioniert) + optionales LLM-Reranking.

    Additiv zu ``search_similar`` — bricht dessen Signatur/Verhalten NICHT,
    ruft es intern für den Vektor-Zweig auf. Für high-stakes RAG-Pfade
    (Persona-Treue), wo reines Top-K-Cosine nicht reicht (Doktrin:
    "Reranking bei hohen Stakes", "Hybrid schlägt Purismus").

    Ablauf:
    1. Vektor-Zweig: search_similar() (bestehende Cosine-Suche, unverändert).
    2. Lexical-Zweig: content_tsv/ts_rank_cd (falls use_hybrid und Spalte
       vorhanden — sonst automatischer Fallback auf reinen Vektor-Zweig).
    3. RRF-Fusion beider Ranglisten (services.rag_rerank.rrf_fuse).
    4. Optionales Listwise-LLM-Rerank der fusionierten Top-Kandidaten
       (services.rag_rerank.llm_rerank) — fällt bei jedem Fehler auf die
       RRF-Reihenfolge zurück.

    Args:
        over_fetch:  Wie viele Kandidaten pro Zweig geholt werden, bevor
                     fusioniert/reranked wird (mehr als `limit`, damit RRF/
                     Rerank echte Auswahl haben).
        use_hybrid:  False ⇒ überspringt den Lexical-Zweig (reines Vektor-RRF
                     mit nur einer Liste, äquivalent zu search_similar-Reihenfolge).
        use_rerank:  False ⇒ überspringt den LLM-Rerank-Schritt (nur RRF-Fusion).

    Returns:
        Liste von dicts im gleichen Shape wie ``search_similar``-Ergebnisse,
        Top-``limit``, neu geordnet nach Fusion (+ optional Rerank).
    """
    from services.rag_rerank import llm_rerank, rrf_fuse

    vector_hits = await search_similar(
        db,
        tenant_id=tenant_id,
        query_text=query_text,
        limit=over_fetch,
        min_similarity=min_similarity,
        classification=classification,
        source_types=source_types,
    )
    if not vector_hits:
        return []

    lexical_hits: list[dict] = []
    if use_hybrid and query_text and query_text.strip():
        lexical_hits = await _lexical_search(
            db,
            tenant_id=tenant_id,
            query_text=query_text,
            limit=over_fetch,
            classification=classification,
            source_types=source_types,
        )

    by_id = {h["id"]: h for h in vector_hits}
    for h in lexical_hits:
        by_id.setdefault(h["id"], h)

    vector_ids = [h["id"] for h in vector_hits]
    lexical_ids = [h["id"] for h in lexical_hits]
    fused_ids = rrf_fuse(vector_ids, lexical_ids) if lexical_ids else vector_ids
    fused = [by_id[cid] for cid in fused_ids if cid in by_id][:over_fetch]

    if use_rerank and query_text and query_text.strip():
        return llm_rerank(query_text, fused, tenant_id, top_n=limit)
    return fused[:limit]
