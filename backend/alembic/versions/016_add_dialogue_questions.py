"""Add dialogue_questions table for Dialogic MCP Layer.

Revision ID: 016
Revises: 015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '016'
down_revision = '015_add_source_keywords'


def upgrade() -> None:
    op.create_table(
        'dialogue_questions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('source_item_id', UUID(as_uuid=True), sa.ForeignKey('source_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('transcript_reference', sa.Text()),
        sa.Column('why_relevant', sa.Text()),
        sa.Column('target_angle', sa.String(50)),
        sa.Column('order_index', sa.Integer(), server_default='0'),
        sa.Column('answer_text', sa.Text()),
        sa.Column('answered_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
    )
    op.create_index('idx_dialogue_questions_item', 'dialogue_questions', ['source_item_id'])
    op.create_index('idx_dialogue_questions_tenant', 'dialogue_questions', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('idx_dialogue_questions_tenant', 'dialogue_questions')
    op.drop_index('idx_dialogue_questions_item', 'dialogue_questions')
    op.drop_table('dialogue_questions')
