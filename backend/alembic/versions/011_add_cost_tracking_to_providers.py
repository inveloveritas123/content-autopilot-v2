"""Add cost tracking fields to llm_providers.

Revision ID: 011
Revises: 010
"""
from alembic import op
import sqlalchemy as sa

revision = '011'
down_revision = '010'

def upgrade() -> None:
    op.add_column('llm_providers', sa.Column('cost_limit_daily_cents', sa.Integer(), server_default='500'))
    op.add_column('llm_providers', sa.Column('cost_spent_today_cents', sa.Integer(), server_default='0'))
    op.add_column('llm_providers', sa.Column('cost_reset_at', sa.DateTime()))

def downgrade() -> None:
    op.drop_column('llm_providers', 'cost_reset_at')
    op.drop_column('llm_providers', 'cost_spent_today_cents')
    op.drop_column('llm_providers', 'cost_limit_daily_cents')
