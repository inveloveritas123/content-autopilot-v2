"""Phase 7.4 — hook_library (Sammlung performter Hooks)

Revision ID: 044
Revises: 043

Hooks aus content_pieces.content_text (erste 200 chars) sammeln, plus
Manual-Eintragungen vom User. P12 kann beim Generieren als Allow-List
darauf zugreifen.

Quality-Score: kommt entweder aus content_performances (echte Daten)
oder als 0.0 default — Hook-Library funktioniert auch ohne Performance-
Daten als reine Curated-List.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hook_library",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_piece_id", UUID(as_uuid=True), sa.ForeignKey("content_pieces.id", ondelete="SET NULL"), nullable=True),
        sa.Column("hook_text", sa.Text, nullable=False),
        sa.Column("hook_type", sa.String(20), nullable=False, server_default="general"),  # general/hook/story/these/manual
        sa.Column("performance_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("used_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.Column("metadata", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.execute(
        "ALTER TABLE hook_library ADD CONSTRAINT ck_hook_library_type "
        "CHECK (hook_type IN ('general', 'hook', 'story', 'these', 'manual'))"
    )
    op.create_index("idx_hook_library_tenant_perf", "hook_library", ["tenant_id", "performance_score"])
    op.create_index("idx_hook_library_tenant_type", "hook_library", ["tenant_id", "hook_type"])


def downgrade() -> None:
    op.drop_index("idx_hook_library_tenant_type", table_name="hook_library")
    op.drop_index("idx_hook_library_tenant_perf", table_name="hook_library")
    op.drop_table("hook_library")
