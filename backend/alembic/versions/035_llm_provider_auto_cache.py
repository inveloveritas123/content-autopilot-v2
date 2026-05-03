"""Add auto_cache flag to llm_providers (#127 B)

Per-Provider opt-in für Requesty.ai Auto-Caching. Default TRUE — alle
existierenden Requesty-Provider profitieren sofort vom Caching ohne
manuelle Migration. Wer gezielt deaktivieren will, kann den Toggle im
Provider-UI (#124) umstellen.

Revision ID: 035
Revises: 034
"""
from alembic import op
import sqlalchemy as sa


revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_providers",
        sa.Column(
            "auto_cache",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("llm_providers", "auto_cache")
