"""backtest_runs table

Revision ID: 023
Revises: 022
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('backtest_runs',
        sa.Column('id', sa.String(36), primary_key=True),  # UUID as string
        sa.Column('tenant_id', sa.String(100), nullable=False),
        sa.Column('current_model_id', sa.String(200)),
        sa.Column('candidate_model_id', sa.String(200), nullable=False),
        sa.Column('post_ids', JSONB()),  # list of post UUIDs
        sa.Column('status', sa.String(20), server_default='pending'),  # pending/running/completed/failed
        sa.Column('results', JSONB()),  # list of per-post results
        sa.Column('summary', JSONB()),  # {total, passed, score_pct}
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('finished_at', sa.DateTime()),
        sa.Column('created_by', sa.String(100)),  # admin user
    )


def downgrade():
    op.drop_table('backtest_runs')
