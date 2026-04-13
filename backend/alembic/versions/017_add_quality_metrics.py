"""Add quality_metrics table for Analytics Phase 2.

Revision ID: 017
Revises: 016
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '017'
down_revision = '016'


def upgrade() -> None:
    op.create_table(
        'quality_metrics',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('source_item_id', UUID(as_uuid=True), sa.ForeignKey('source_items.id', ondelete='CASCADE')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('step', sa.String(50), nullable=False),
        sa.Column('model_used', sa.String(150)),
        sa.Column('input_tokens', sa.Integer()),
        sa.Column('output_tokens', sa.Integer()),
        sa.Column('cost_cents', sa.Float()),
        sa.Column('latency_ms', sa.Integer()),
        sa.Column('completeness_score', sa.Float()),
        sa.Column('accuracy_score', sa.Float()),
        sa.Column('relevance_score', sa.Float()),
        sa.Column('overall_score', sa.Float()),
        sa.Column('user_rating', sa.Integer()),
        sa.Column('user_edited', sa.Boolean()),
        sa.Column('edit_distance', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
    )
    op.create_index('idx_quality_metrics_item', 'quality_metrics', ['source_item_id'])
    op.create_index('idx_quality_metrics_tenant_step', 'quality_metrics', ['tenant_id', 'step'])
    op.create_index('idx_quality_metrics_model', 'quality_metrics', ['model_used'])


def downgrade() -> None:
    op.drop_index('idx_quality_metrics_model', 'quality_metrics')
    op.drop_index('idx_quality_metrics_tenant_step', 'quality_metrics')
    op.drop_index('idx_quality_metrics_item', 'quality_metrics')
    op.drop_table('quality_metrics')
