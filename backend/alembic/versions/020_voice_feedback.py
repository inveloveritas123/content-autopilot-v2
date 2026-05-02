"""Add voice_feedback table for "So sage ich das nicht" feedback.

Revision ID: 020
Revises: 019
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '020'
down_revision = '019'


def upgrade() -> None:
    op.create_table(
        'voice_feedback',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('post_id', UUID(as_uuid=True), nullable=False),
        sa.Column('problem_part', sa.Text(), nullable=False),
        sa.Column('user_note', sa.Text(), nullable=False),
        sa.Column('processed_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_voice_feedback_tenant'),
        sa.ForeignKeyConstraint(['post_id'], ['content_pieces.id'], name='fk_voice_feedback_post'),
    )
    op.create_index(
        'ix_voice_feedback_tenant_processed',
        'voice_feedback',
        ['tenant_id', 'processed_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_voice_feedback_tenant_processed', 'voice_feedback')
    op.drop_table('voice_feedback')
