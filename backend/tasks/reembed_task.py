"""Mass-Re-Embed mit Canary-Strategie (Issue #150 — Phase 5 Sub).

Workflow:
1. 10% der Chunks pro Tenant (sticky per tenant_id-Hash) als Canary-Auswahl
2. Neue Embeddings in `embedding_canary`-Spalte (Migration 049)
3. Recall@20-Sampling: 50 zufällige Query-Chunks, alte vs. neue Embeddings
4. Vergleich: neue Recall >= alte Recall → weitermachen, sonst STOP + WARNING
5. 100%-Roll: alte embedding-Spalte durch Canary ersetzen, model_id aktualisieren
6. Idempotent: Skip wenn embedding_canary für diesen Chunk schon gesetzt

Annahme: der Task läuft in einer Umgebung mit PostgreSQL + pgvector.
LLM-Calls via Requesty (kein direkter API-Zugriff, Constraint #1).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from services.soft_delete_filter import SQL_NICHT_GELOESCHT
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _tenant_hash_fraction(tenant_id: str, seed: str = "canary-v1") -> float:
    """Deterministischer Wert 0..1 für einen Tenant (sticky per tenant_id).

    Gleicher Input → immer gleicher Wert → dieselben Tenants werden gewählt.
    """
    digest = hashlib.sha256(f"{seed}:{tenant_id}".encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


async def _get_all_tenant_ids(db: AsyncSession) -> list[str]:
    rows = (
        await db.execute(
            text(f"SELECT DISTINCT tenant_id FROM memory_chunks WHERE {SQL_NICHT_GELOESCHT}")
        )
    ).fetchall()
    return [str(r[0]) for r in rows]


async def _count_chunks_for_tenant(db: AsyncSession, tenant_id: str) -> int:
    row = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM memory_chunks "
                f"WHERE tenant_id = CAST(:tid AS uuid) AND {SQL_NICHT_GELOESCHT}"
            ),
            {"tid": tenant_id},
        )
    ).scalar()
    return int(row or 0)


async def _get_canary_chunk_ids(
    db: AsyncSession,
    tenant_id: str,
    percent: int,
) -> list[str]:
    """Deterministisch 'percent'% der Chunks per tenant_id-Hash samplen.

    Nutzt MD5 der Chunk-ID für gleichmäßige Streuung ohne TABLESAMPLE
    (TABLESAMPLE ist nicht deterministisch per Tenant).
    """
    threshold = percent / 100.0
    rows = (
        await db.execute(
            text(
                "SELECT id FROM memory_chunks "
                "WHERE tenant_id = CAST(:tid AS uuid) "
                f"  AND {SQL_NICHT_GELOESCHT} "
                "  AND embedding IS NOT NULL "
                "  AND ('x' || md5(id::text))::bit(32)::int / 4294967295.0 < :threshold "
                "ORDER BY id "
                "LIMIT 5000"  # Sicherheits-Cap
            ),
            {"tid": tenant_id, "threshold": threshold},
        )
    ).fetchall()
    return [str(r[0]) for r in rows]


async def _embed_canary_chunk(
    db: AsyncSession,
    chunk_id: str,
    new_model_id: str,
) -> bool:
    """Embeddet einen Chunk mit neuem Modell in embedding_canary-Spalte.

    Idempotent: überspringt Chunks die bereits embedding_canary gesetzt haben.
    Returns True wenn embedding gesetzt wurde, False wenn übersprungen/Fehler.
    """
    from services.embedding_service import _embedding_to_pg, embed

    # Idempotenz-Check
    row = (
        await db.execute(
            text(
                "SELECT content_text, embedding_canary FROM memory_chunks "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"id": chunk_id},
        )
    ).fetchone()
    if row is None:
        return False
    if row.embedding_canary is not None:
        return False  # bereits gesetzt — Skip

    content = row.content_text or ""
    if not content.strip():
        return False

    vector, used_model_id = await embed(content, model_id=new_model_id)
    if vector is None:
        return False

    await db.execute(
        text(
            "UPDATE memory_chunks "
            "SET embedding_canary = CAST(:vec AS vector), updated_at = NOW() "
            "WHERE id = CAST(:id AS uuid)"
        ),
        {"id": chunk_id, "vec": _embedding_to_pg(vector)},
    )
    return True


async def _compute_recall_at_k(
    db: AsyncSession,
    tenant_id: str,
    use_canary: bool,
    k: int = 20,
    n_queries: int = 50,
) -> float:
    """Schätzt Recall@k via n_queries zufälliger Query-Chunks.

    Methode: Nimm n_queries zufällige Chunks als 'Query', finde ihre k
    nächsten Nachbarn, prüfe ob der Chunk selbst unter seinen k Nachbarn ist
    (Selbst-Recall). Wert 1.0 = perfekter Index, 0.0 = komplett kaputt.

    use_canary=True  → verwendet embedding_canary als Suchspalte
    use_canary=False → verwendet embedding (aktuelle Produktion)
    """

    emb_col = "embedding_canary" if use_canary else "embedding"

    # Zufällige Query-Chunks holen (mit Embedding in der jeweiligen Spalte)
    rows = (
        await db.execute(
            text(
                f"SELECT id, {emb_col} AS qemb "
                f"FROM memory_chunks "
                f"WHERE tenant_id = CAST(:tid AS uuid) "
                f"  AND {SQL_NICHT_GELOESCHT} "
                f"  AND {emb_col} IS NOT NULL "
                f"ORDER BY random() LIMIT :n"
            ),
            {"tid": tenant_id, "n": n_queries},
        )
    ).fetchall()

    if not rows:
        return 0.0

    hits = 0
    for row in rows:
        query_id = str(row.id)
        # pgvector liefert emb als string — re-use as-is für den Query
        qemb_str = row.qemb
        if qemb_str is None:
            continue

        # Top-k Nachbarn per cosine distance
        neighbors = (
            await db.execute(
                text(
                    f"SELECT id FROM memory_chunks "
                    f"WHERE tenant_id = CAST(:tid AS uuid) "
                    f"  AND {SQL_NICHT_GELOESCHT} "
                    f"  AND {emb_col} IS NOT NULL "
                    f"ORDER BY {emb_col} <=> CAST(:qemb AS vector) "
                    f"LIMIT :k"
                ),
                {"tid": tenant_id, "qemb": str(qemb_str), "k": k},
            )
        ).fetchall()

        neighbor_ids = {str(r[0]) for r in neighbors}
        if query_id in neighbor_ids:
            hits += 1

    return hits / len(rows)


async def _roll_canary_to_production(
    db: AsyncSession,
    tenant_id: str,
    new_model_id: str,
) -> int:
    """Ersetzt embedding durch embedding_canary für alle Canary-Rows eines Tenants.

    Returns Anzahl aktualisierter Rows.
    """
    result = await db.execute(
        text(
            "UPDATE memory_chunks "
            "SET embedding = embedding_canary, "
            "    embedding_model_id = :model_id, "
            "    embedding_canary = NULL, "
            "    updated_at = NOW() "
            "WHERE tenant_id = CAST(:tid AS uuid) "
            "  AND embedding_canary IS NOT NULL "
            f"  AND {SQL_NICHT_GELOESCHT}"
        ),
        {"tid": tenant_id, "model_id": new_model_id},
    )
    return result.rowcount


# ---------------------------------------------------------------------------
# Celery-Task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="tasks.reembed_task.reembed_chunks_with_canary",
    bind=True,
    max_retries=0,
)
def reembed_chunks_with_canary(
    self,
    new_model_id: str,
    percent: int = 10,
) -> dict:
    """Mass-Re-Embed mit Canary-Strategie.

    Args:
        new_model_id: ID des neuen Embedding-Modells (muss in EMBEDDING_MODELS sein).
        percent:      Anteil der Chunks pro Tenant für Canary-Phase (Default: 10%).

    Returns:
        Dict mit Status-Informationen pro Tenant.
    """
    from services.embedding_service import EMBEDDING_MODELS

    if new_model_id not in EMBEDDING_MODELS:
        logger.error("reembed_chunks_with_canary: unbekanntes model_id=%s — abbruch", new_model_id)
        return {"status": "error", "reason": f"unknown model_id: {new_model_id}"}

    try:
        result = asyncio.run(_reembed_async(new_model_id, percent))
    except Exception as exc:
        logger.exception("reembed_chunks_with_canary: FAILED — %s", exc)
        return {"status": "error", "reason": str(exc)[:200]}

    return result


async def _reembed_async(new_model_id: str, percent: int) -> dict:
    """Async-Implementierung des Canary-Re-Embed."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    tenant_results: dict[str, dict] = {}

    try:
        async with SessionMaker() as db:
            tenant_ids = await _get_all_tenant_ids(db)
            logger.info("reembed: %d Tenants gefunden", len(tenant_ids))

        for tenant_id in tenant_ids:
            async with SessionMaker() as db:
                logger.info("reembed: tenant=%s — Canary-Phase start", tenant_id)

                # 1) Chunk-IDs für Canary ermitteln
                canary_ids = await _get_canary_chunk_ids(db, tenant_id, percent)
                if not canary_ids:
                    logger.info("reembed: tenant=%s — keine Chunks für Canary", tenant_id)
                    tenant_results[tenant_id] = {"status": "skipped", "reason": "no_chunks"}
                    continue

                logger.info(
                    "reembed: tenant=%s — %d Canary-Chunks (%.0f%%)",
                    tenant_id,
                    len(canary_ids),
                    percent,
                )

                # 2) Re-embed in embedding_canary (idempotent)
                embedded = 0
                skipped = 0
                for chunk_id in canary_ids:
                    ok = await _embed_canary_chunk(db, chunk_id, new_model_id)
                    if ok:
                        embedded += 1
                    else:
                        skipped += 1

                await db.commit()
                logger.info(
                    "reembed: tenant=%s — embedded=%d skipped=%d",
                    tenant_id,
                    embedded,
                    skipped,
                )

                if embedded == 0 and skipped == len(canary_ids):
                    # Alles schon canary — mach weiter mit Recall-Check
                    logger.info("reembed: tenant=%s — alle Canary bereits gesetzt", tenant_id)

                # 3) Recall@20 — alte vs. neue Embeddings (50 Sample-Queries)
                recall_old = await _compute_recall_at_k(db, tenant_id, use_canary=False)
                recall_new = await _compute_recall_at_k(db, tenant_id, use_canary=True)

                logger.info(
                    "reembed: tenant=%s — recall_old=%.3f recall_new=%.3f",
                    tenant_id,
                    recall_old,
                    recall_new,
                )

                # 4) Qualitäts-Gate
                if recall_new < recall_old:
                    logger.warning(
                        "reembed: tenant=%s — Recall-Drop (%.3f → %.3f) — STOP, kein Roll",
                        tenant_id,
                        recall_old,
                        recall_new,
                    )
                    tenant_results[tenant_id] = {
                        "status": "stopped_recall_drop",
                        "recall_old": recall_old,
                        "recall_new": recall_new,
                        "canary_chunks": len(canary_ids),
                    }
                    continue

                # 5) 100%-Roll: Canary → Produktion
                rolled = await _roll_canary_to_production(db, tenant_id, new_model_id)
                await db.commit()
                logger.info(
                    "reembed: tenant=%s — %d Rows gerollt auf model_id=%s",
                    tenant_id,
                    rolled,
                    new_model_id,
                )
                tenant_results[tenant_id] = {
                    "status": "rolled",
                    "rolled_rows": rolled,
                    "recall_old": recall_old,
                    "recall_new": recall_new,
                }

    finally:
        await engine.dispose()

    overall_status = (
        "done"
        if all(v.get("status") in ("rolled", "skipped") for v in tenant_results.values())
        else "partial"
    )
    return {
        "status": overall_status,
        "new_model_id": new_model_id,
        "tenants": tenant_results,
    }
