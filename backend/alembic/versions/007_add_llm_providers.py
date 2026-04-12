"""Add llm_providers table.

Revision ID: 007
Revises: 006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '007'
down_revision = '006'

def upgrade() -> None:
    op.create_table(
        'llm_providers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('provider_type', sa.String(50), nullable=False),
        sa.Column('api_key_encrypted', sa.String(500)),
        sa.Column('base_url', sa.String(500)),
        sa.Column('model_name', sa.String(100)),
        sa.Column('task_assignment', sa.String(50), server_default='all'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('is_default', sa.Boolean(), server_default='false'),
        sa.Column('last_test_at', sa.DateTime()),
        sa.Column('last_test_status', sa.String(20)),
        sa.Column('last_test_error', sa.String(500)),
        sa.Column('config', JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

def downgrade() -> None:
    op.drop_table('llm_providers')
