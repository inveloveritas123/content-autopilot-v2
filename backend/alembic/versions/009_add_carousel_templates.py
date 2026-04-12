"""Add carousel_templates table.

Revision ID: 009
Revises: 008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '009'
down_revision = '008'

def upgrade() -> None:
    op.create_table(
        'carousel_templates',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slides_config', JSONB, server_default='{}'),
        sa.Column('brand_colors', JSONB, server_default='{}'),
        sa.Column('font_config', JSONB, server_default='{}'),
        sa.Column('is_default', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

def downgrade() -> None:
    op.drop_table('carousel_templates')
