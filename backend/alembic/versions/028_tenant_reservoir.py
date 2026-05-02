"""tenant_reservoir table for hallucination prevention

Revision ID: 028
Revises: 027
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY, TEXT as PG_TEXT

revision = '028'
down_revision = '027'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tenant_reservoir',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=False),   # 'transcript', 'article', 'voice_profile'
        sa.Column('source_ref', sa.String(500), nullable=True),    # URL, file path, or ID
        sa.Column('content_text', sa.Text, nullable=False),
        sa.Column('extracted_quotes', ARRAY(PG_TEXT), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_reservoir_tenant', 'tenant_reservoir', ['tenant_id'])


def downgrade():
    op.drop_index('ix_reservoir_tenant', 'tenant_reservoir')
    op.drop_table('tenant_reservoir')
