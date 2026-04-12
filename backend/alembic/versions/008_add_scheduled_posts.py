"""Add scheduled_posts table.

Revision ID: 008
Revises: 007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '008'
down_revision = '007'

def upgrade() -> None:
    op.create_table(
        'scheduled_posts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('content_piece_id', UUID(as_uuid=True), sa.ForeignKey('content_pieces.id'), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(20), server_default='scheduled'),
        sa.Column('linkedin_post_id', sa.String(100)),
        sa.Column('published_at', sa.DateTime()),
        sa.Column('error_message', sa.String(500)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_scheduled_posts_tenant_status', 'scheduled_posts', ['tenant_id', 'status'])
    op.create_index('idx_scheduled_posts_scheduled_at', 'scheduled_posts', ['scheduled_at'])

def downgrade() -> None:
    op.drop_table('scheduled_posts')
