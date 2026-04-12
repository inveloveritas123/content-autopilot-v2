"""Add views, keywords, description, channel_name to source_items

Revision ID: 002
Revises: 001
Create Date: 2026-04-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source_items", sa.Column("description", sa.Text))
    op.add_column("source_items", sa.Column("view_count", sa.Integer))
    op.add_column("source_items", sa.Column("view_history", JSONB))
    op.add_column("source_items", sa.Column("keywords", JSONB))
    op.add_column("source_items", sa.Column("channel_name", sa.String(255)))


def downgrade() -> None:
    op.drop_column("source_items", "channel_name")
    op.drop_column("source_items", "keywords")
    op.drop_column("source_items", "view_history")
    op.drop_column("source_items", "view_count")
    op.drop_column("source_items", "description")
