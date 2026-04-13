"""add keywords column to sources

Revision ID: 015_add_source_keywords
Revises: 014_widen_external_id
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = '015_add_source_keywords'
down_revision = '014_widen_external_id'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sources', sa.Column('keywords', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('sources', 'keywords')
