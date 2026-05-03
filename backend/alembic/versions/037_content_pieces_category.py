"""Add category column to content_pieces (Phase 4.1 / #145)

Revision ID: 037
Revises: 036
"""
from alembic import op
import sqlalchemy as sa


revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


CATEGORY_VALUES = ("news", "persoenlich", "trust", "praxis")


def upgrade() -> None:
    op.add_column(
        "content_pieces",
        sa.Column("category", sa.String(20), nullable=True),
    )
    # CHECK-Constraint nach gültigen Werten + NULL erlaubt (Backfill optional)
    op.create_check_constraint(
        "ck_content_pieces_category",
        "content_pieces",
        f"category IS NULL OR category IN {CATEGORY_VALUES}",
    )
    op.create_index(
        "idx_content_pieces_tenant_category",
        "content_pieces",
        ["tenant_id", "category"],
    )


def downgrade() -> None:
    op.drop_index("idx_content_pieces_tenant_category", table_name="content_pieces")
    op.drop_constraint("ck_content_pieces_category", "content_pieces", type_="check")
    op.drop_column("content_pieces", "category")
