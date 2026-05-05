"""embedding_model_id Spalte + Canary-Spalte in memory_chunks

Revision ID: 049
Revises: 048
Create Date: 2026-05-04

Issue #150: pgvector — Index-Defaults + Embedding-Versionierung + Re-Embed-Job.

- embedding_model_id: VARCHAR(64) nullable, Backfill auf 'gemini-embedding-001-1536d'
- embedding_canary: vector(1536) nullable, temporäre Spalte für Canary-Re-Embed
- Partial Index auf embedding_model_id WHERE NOT NULL
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade():
    # 1) embedding_model_id — Versionierungs-Spalte
    op.add_column(
        "memory_chunks",
        sa.Column("embedding_model_id", sa.String(64), nullable=True),
    )

    # 2) embedding_canary — temporäre Spalte für Canary-Re-Embed-Task
    #    Nutzt pgvector-Typ via server_default-freies raw DDL (kein SQLAlchemy-Typ für vector)
    op.execute(
        sa.text(
            "ALTER TABLE memory_chunks "
            "ADD COLUMN embedding_canary vector(1536)"
        )
    )

    # 3) Backfill bestehender Rows: Standard-Modell (was bisher genutzt wurde)
    op.execute(
        sa.text(
            "UPDATE memory_chunks "
            "SET embedding_model_id = 'gemini-embedding-001-1536d' "
            "WHERE embedding_model_id IS NULL"
        )
    )

    # 4) Partial Index auf embedding_model_id — nur Rows die einen Wert haben
    op.create_index(
        "idx_memory_chunks_embedding_model",
        "memory_chunks",
        ["embedding_model_id"],
        postgresql_where=sa.text("embedding_model_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index(
        "idx_memory_chunks_embedding_model",
        table_name="memory_chunks",
    )
    op.drop_column("memory_chunks", "embedding_canary")
    op.drop_column("memory_chunks", "embedding_model_id")
