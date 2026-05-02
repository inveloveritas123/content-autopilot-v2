"""tenant_branding table for carousel brand customization

Revision ID: 029
Revises: 028
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '029'
down_revision = '028'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tenant_branding',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('primary_color', sa.String(7), nullable=False, server_default='#0F766E'),
        sa.Column('secondary_color', sa.String(7), nullable=False, server_default='#F59E0B'),
        sa.Column('font_family', sa.String(100), nullable=False, server_default='Helvetica'),
        sa.Column('logo_url', sa.String(500), nullable=True),
        sa.Column('watermark_text', sa.String(200), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), onupdate=sa.text('NOW()')),
    )


def downgrade():
    op.drop_table('tenant_branding')
