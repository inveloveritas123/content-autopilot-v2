"""Add audio_url and content_type to source_items.

Revision ID: 004
Revises: 003
"""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'

def upgrade() -> None:
    op.add_column('source_items', sa.Column('audio_url', sa.String(500), nullable=True))
    op.add_column('source_items', sa.Column('content_type', sa.String(50), nullable=True))

def downgrade() -> None:
    op.drop_column('source_items', 'content_type')
    op.drop_column('source_items', 'audio_url')
