"""widen external_id from 100 to 512 chars

Revision ID: 014_widen_external_id
Revises: 013_add_llm_call_logs_and_task_assignments
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = '014_widen_external_id'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('source_items', 'external_id',
                    existing_type=sa.String(length=100),
                    type_=sa.String(length=512),
                    existing_nullable=False)


def downgrade():
    op.alter_column('source_items', 'external_id',
                    existing_type=sa.String(length=512),
                    type_=sa.String(length=100),
                    existing_nullable=False)
