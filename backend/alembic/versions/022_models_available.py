"""models_available table

Revision ID: 022
Revises: 021
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('models_available',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('provider', sa.String(50), nullable=False),  # 'requesty', 'anthropic', 'vertex'
        sa.Column('model_id', sa.String(200), nullable=False, unique=True),
        sa.Column('display_name', sa.String(200)),
        sa.Column('first_seen_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('deprecated_at', sa.DateTime()),
        sa.Column('meta', JSONB()),  # extra info
    )


def downgrade():
    op.drop_table('models_available')
