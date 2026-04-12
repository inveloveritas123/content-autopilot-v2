"""Add llm_call_logs table and analysis_summary to source_items.

Revision ID: 013
Revises: 012
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '013'
down_revision = '012'

def upgrade() -> None:
    op.create_table(
        'llm_call_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('provider_id', UUID(as_uuid=True), sa.ForeignKey('llm_providers.id')),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), server_default='0'),
        sa.Column('cost_cents', sa.Float(), server_default='0'),
        sa.Column('duration_ms', sa.Integer(), server_default='0'),
        sa.Column('success', sa.Boolean(), server_default='true'),
        sa.Column('error_message', sa.String(500)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_llm_call_logs_tenant_date', 'llm_call_logs', ['tenant_id', 'created_at'])

    # Analysis summary for context compression
    op.add_column('source_items', sa.Column('analysis_summary', sa.Text()))

def downgrade() -> None:
    op.drop_column('source_items', 'analysis_summary')
    op.drop_table('llm_call_logs')
