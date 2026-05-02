"""tenant kill-switch columns

Revision ID: 026
Revises: 025
"""
from alembic import op
import sqlalchemy as sa

revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('tenants', sa.Column('enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('tenants', sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tenants', sa.Column('disabled_by', sa.String(100), nullable=True))
    op.add_column('tenants', sa.Column('disabled_reason', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('tenants', 'disabled_reason')
    op.drop_column('tenants', 'disabled_by')
    op.drop_column('tenants', 'disabled_at')
    op.drop_column('tenants', 'enabled')
