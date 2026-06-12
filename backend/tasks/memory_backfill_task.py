"""Backfill-Task für nicht-embeddete memory_chunks (Phase 5 Folge).

Findet memory_chunks ohne embedding (z.B. wenn Embedding-API zur
Speicherzeit Budget-exceeded war), holt sie batchweise und embedded
sie nachträglich. Auch Klassifikation-Backfill für unklassifizierte.

Triggers:
  - manuelle CLI: python -m tasks.memory_backfill_task --limit 50
  - Celery-Cron: stündlich, 100 chunks pro Run (rate-limit-safe)
"""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

DEFAULT_BATCH_LIMIT = 100


async def _backfill_async(limit: int) -> dict:
    """Eine Backfill-Runde — async damit embedding_service genutzt werden kann."""
    from services.embedding_service import _embedding_to_pg, classify_chunk, embed_text

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    embedded_count = 0
    classified_count = 0
    failed_count = 0
    try:
        async with SessionMaker() as db:
            # 1) Chunks ohne embedding
            rows = (
                await db.execute(
                    text(
                        "SELECT id, content_text, classification "
                        "FROM memory_chunks "
                        "WHERE embedding IS NULL "
                        "ORDER BY created_at DESC "
                        "LIMIT :lim"
                    ),
                    {"lim": limit},
                )
            ).fetchall()

            for r in rows:
                chunk_id = str(r.id)
                content = r.content_text or ""
                if not content.strip():
                    continue

                emb = await embed_text(content)
                cls = r.classification
                if cls is None and content.strip():
                    cls = await classify_chunk(content)

                if emb is None and cls == r.classification:
                    failed_count += 1
                    continue  # nichts zu tun für diesen Chunk

                set_parts = []
                params: dict = {"id": chunk_id}
                if emb is not None:
                    set_parts.append("embedding = CAST(:emb AS vector)")
                    params["emb"] = _embedding_to_pg(emb)
                    embedded_count += 1
                if cls is not None and cls != r.classification:
                    set_parts.append("classification = :cls")
                    params["cls"] = cls
                    classified_count += 1
                if not set_parts:
                    continue
                set_parts.append("updated_at = now()")
                await db.execute(
                    text(
                        f"UPDATE memory_chunks SET {', '.join(set_parts)} WHERE id = CAST(:id AS uuid)"
                    ),
                    params,
                )
            await db.commit()

            # 2) Bonus-Pass: Chunks mit embedding aber ohne classification
            unclassified = (
                await db.execute(
                    text(
                        "SELECT id, content_text "
                        "FROM memory_chunks "
                        "WHERE classification IS NULL AND length(content_text) >= 20 "
                        "ORDER BY created_at DESC "
                        "LIMIT :lim"
                    ),
                    {"lim": min(limit, 50)},
                )
            ).fetchall()

            for r in unclassified:
                cls = await classify_chunk(r.content_text or "")
                if cls:
                    await db.execute(
                        text(
                            "UPDATE memory_chunks SET classification = :cls, updated_at = now() WHERE id = :id"
                        ),
                        {"id": r.id, "cls": cls},
                    )
                    classified_count += 1
            await db.commit()
    finally:
        await engine.dispose()

    return {
        "embedded": embedded_count,
        "classified": classified_count,
        "failed": failed_count,
    }


@celery_app.task(name="tasks.memory_backfill_task.run_backfill", bind=True, max_retries=0)
def run_backfill(self, limit: int = DEFAULT_BATCH_LIMIT) -> dict:
    """Celery-Task — wird stündlich von celery-beat angestoßen.

    Idempotent: wenn alles schon embedded, returns {embedded:0, classified:0}.
    """
    try:
        result = asyncio.run(_backfill_async(limit))
    except Exception as exc:
        logger.warning("memory_backfill failed: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}
    logger.info(
        "memory_backfill: embedded=%s classified=%s failed=%s",
        result["embedded"],
        result["classified"],
        result["failed"],
    )
    return {"status": "ok", **result}


# CLI-Entry für manuelle Runs
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill embeddings/classifications")
    parser.add_argument("--limit", type=int, default=DEFAULT_BATCH_LIMIT)
    args = parser.parse_args()
    result = asyncio.run(_backfill_async(args.limit))
    print(json.dumps(result, indent=2))
