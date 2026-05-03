"""Add cache_read_tokens + cache_write_tokens to llm_call_logs

Revision ID: 033
Revises: 032
Create Date: 2026-05-03
"""
from alembic import op
import sqlalchemy as sa

revision = '033'
down_revision = '032'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('llm_call_logs', sa.Column('cache_read_tokens', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('llm_call_logs', sa.Column('cache_write_tokens', sa.Integer(), nullable=True, server_default='0'))


def downgrade():
    op.drop_column('llm_call_logs', 'cache_write_tokens')
    op.drop_column('llm_call_logs', 'cache_read_tokens')
