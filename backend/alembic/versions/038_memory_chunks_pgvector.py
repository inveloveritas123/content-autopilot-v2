"""Phase 5.1 — pgvector + memory_chunks (Unternehmensgedächtnis)

Revision ID: 038
Revises: 037

Aktiviert pgvector im content_autopilot_v2 und legt die memory_chunks-
Tabelle an: Vektorspeicher für unstrukturierte Inhalte (Sprachnotizen,
Fotos, Notizen) mit Tenant-Isolation und semantischer Suche.

Embedding-Dimension: 768 (Vertex text-embedding-004 EU-Region).
HNSW-Index mit cosine-Distance.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


SOURCE_TYPES = (
    "voice_telegram",
    "voice_whatsapp",
    "photo_telegram",
    "photo_whatsapp",
    "manual_note",
    "transcript_extra",
)
CLASSIFICATIONS = ("werte", "stories", "konflikte")


def upgrade() -> None:
    # pgvector-Extension aktivieren (DB-scoped)
    # pgvector-Extension wird außerhalb Alembic als Superuser angelegt (siehe Setup-Guide)
    # Hier nur prüfen ob da; falls nicht: explizit fail-fast.
    res = op.get_bind().execute(sa.text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar()
    if not res:
        raise RuntimeError("pgvector-Extension nicht installiert. Vor dieser Migration als Superuser ausführen: CREATE EXTENSION vector;")

    # memory_chunks-Tabelle
    op.create_table(
        "memory_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_ref", sa.String(500), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(20), nullable=True),
        sa.Column("metadata", JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # embedding-Spalte separat (vector-Type ist alembic-fremd)
    op.execute("ALTER TABLE memory_chunks ADD COLUMN embedding vector(768)")

    # CHECK-Constraints für source_type + classification
    src_list = ", ".join(f"'{s}'" for s in SOURCE_TYPES)
    op.execute(
        f"ALTER TABLE memory_chunks ADD CONSTRAINT ck_memory_chunks_source_type "
        f"CHECK (source_type IN ({src_list}))"
    )
    cls_list = ", ".join(f"'{c}'" for c in CLASSIFICATIONS)
    op.execute(
        f"ALTER TABLE memory_chunks ADD CONSTRAINT ck_memory_chunks_classification "
        f"CHECK (classification IS NULL OR classification IN ({cls_list}))"
    )

    # Reguläre Indexe
    op.create_index("idx_memory_chunks_tenant_type", "memory_chunks", ["tenant_id", "source_type"])
    op.create_index("idx_memory_chunks_tenant_class", "memory_chunks", ["tenant_id", "classification"])
    op.create_index("idx_memory_chunks_created", "memory_chunks", ["tenant_id", "created_at"])

    # HNSW-Index für embedding mit cosine-Distance (nur wenn Embedding gesetzt)
    op.execute(
        "CREATE INDEX idx_memory_chunks_embedding_hnsw "
        "ON memory_chunks USING hnsw (embedding vector_cosine_ops) "
        "WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_memory_chunks_embedding_hnsw")
    op.drop_index("idx_memory_chunks_created", table_name="memory_chunks")
    op.drop_index("idx_memory_chunks_tenant_class", table_name="memory_chunks")
    op.drop_index("idx_memory_chunks_tenant_type", table_name="memory_chunks")
    op.drop_table("memory_chunks")
    # pgvector NICHT droppen — andere Tabellen könnten es später nutzen
