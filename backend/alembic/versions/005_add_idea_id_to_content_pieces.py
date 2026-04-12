"""Add idea_id to content_pieces.

Revision ID: 005
Revises: 004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '005'
down_revision = '004'

def upgrade() -> None:
    op.add_column('content_pieces', sa.Column('idea_id', UUID(as_uuid=True), sa.ForeignKey('content_ideas.id'), nullable=True))

def downgrade() -> None:
    op.drop_column('content_pieces', 'idea_id')
