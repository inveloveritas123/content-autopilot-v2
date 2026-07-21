"""memory_chunks: content_tsv (GENERATED tsvector) + GIN-Index für Hybrid-Search.

Revision ID: 060
Revises: 059
Create Date: 2026-07-21

Ermöglicht den Lexical-Zweig des Hybrid-Retrievals (services/rag_rerank.py
rrf_fuse + services/embedding_service.py search_reranked): reines
Top-K-Cosine (search_similar) verfehlt Fachbegriffe, die lexikalisch klarer
sind als semantisch — Doktrin "Hybrid schlägt Purismus", portiert aus
LunaDeva (knowledge_service._lexical_candidates / search_tsv).

``content_tsv`` ist eine GENERATED STORED Spalte (immer konsistent mit
``content_text``, kein Trigger/Backfill-Risiko). ``to_tsquery``/
``websearch_to_tsquery`` mit Sprache 'german' im Query-Pfad (rag_rerank/
embedding_service), ts_rank_cd für die Relevanz-Sortierung.
"""

from alembic import op

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE memory_chunks ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('german', coalesce(content_text, ''))) STORED"
    )
    op.execute("CREATE INDEX ix_memory_chunks_tsv ON memory_chunks USING gin(content_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memory_chunks_tsv")
    op.execute("ALTER TABLE memory_chunks DROP COLUMN IF EXISTS content_tsv")
