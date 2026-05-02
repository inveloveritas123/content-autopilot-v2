"""Add tenant_bot_config table for Random-Smart-Modus scheduling.

Revision ID: 031
Revises: 030
"""
from alembic import op
import sqlalchemy as sa

revision = '031'
down_revision = '030'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tenant_bot_config',
        sa.Column('id', sa.Text(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('random_smart_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('random_smart_schedule_cron', sa.Text(), nullable=False, server_default=sa.text("'0 9 * * 1,4'")),
        sa.Column('random_smart_paused_until', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('tenant_timezone', sa.Text(), nullable=False, server_default=sa.text("'Europe/Berlin'")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id'),
    )


def downgrade():
    op.drop_table('tenant_bot_config')
