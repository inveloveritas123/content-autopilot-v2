"""Phase 5 — Embedding-Dim von 768 auf 1536 umstellen

Revision ID: 039
Revises: 038

Requesty.ai routet `vertex/text-embedding-004` (768-dim) NICHT;
verfügbar ist `openai/text-embedding-3-small` mit 1536-dim. Da
memory_chunks zum Zeitpunkt dieser Migration noch leer ist
(Phase 5 wurde gerade in 038 angelegt), kein Backfill nötig:
einfach DROP+ADD der embedding-Spalte und Index neu.
"""
from alembic import op


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PARTIAL HNSW-Index zuerst weg, sonst kann Spalte nicht gedroppt werden
    op.execute("DROP INDEX IF EXISTS idx_memory_chunks_embedding_hnsw")
    op.execute("ALTER TABLE memory_chunks DROP COLUMN embedding")
    op.execute("ALTER TABLE memory_chunks ADD COLUMN embedding vector(1536)")
    op.execute(
        "CREATE INDEX idx_memory_chunks_embedding_hnsw "
        "ON memory_chunks USING hnsw (embedding vector_cosine_ops) "
        "WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_memory_chunks_embedding_hnsw")
    op.execute("ALTER TABLE memory_chunks DROP COLUMN embedding")
    op.execute("ALTER TABLE memory_chunks ADD COLUMN embedding vector(768)")
    op.execute(
        "CREATE INDEX idx_memory_chunks_embedding_hnsw "
        "ON memory_chunks USING hnsw (embedding vector_cosine_ops) "
        "WHERE embedding IS NOT NULL"
    )
