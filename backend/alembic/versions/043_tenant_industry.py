"""Phase 4.4 — tenant.industry-Spalte + industry_context-JSONB

Revision ID: 043
Revises: 042

Tenants brauchen explizite Branche für Branchen-spezifisches Relevanz-
Scoring (Eric-Vorgabe). Wo industry leer ist (Backwards-Compat), läuft
das Scoring generisch — kein Bruch.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("industry", sa.String(100), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("industry_context", JSONB, server_default=sa.text("'{}'::jsonb")),
    )
    # Index für branchen-spezifische Reports
    op.create_index("idx_tenants_industry", "tenants", ["industry"])


def downgrade() -> None:
    op.drop_index("idx_tenants_industry", table_name="tenants")
    op.drop_column("tenants", "industry_context")
    op.drop_column("tenants", "industry")
