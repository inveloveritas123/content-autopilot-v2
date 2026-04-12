"""Add is_archived to source_items.

Revision ID: 006
Revises: 005
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'

def upgrade() -> None:
    op.add_column('source_items', sa.Column('is_archived', sa.Boolean(), server_default='false', nullable=False))

def downgrade() -> None:
    op.drop_column('source_items', 'is_archived')
