"""Add project_id to wizard_session — project-scoped wizard sessions

Revision ID: 035
Revises: 034
Create Date: 2026-05-03

Motivation: #116 Cowork-Review point 2 — with #113 (Multi-Brand-Voice per
Project), wizard sessions must be project-scoped. Without this column, switching
from project A to project B and starting the wizard would resume project A's
in_progress session instead of creating a fresh one for project B.

Nullable: existing sessions belong to the tenant's global (NULL) slot,
consistent with how all brand-voice tables handle the pre-project era.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '035'
down_revision = '034'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('wizard_session',
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True)
    )
    op.create_index('ix_wizard_session_tenant_project', 'wizard_session', ['tenant_id', 'project_id'])


def downgrade():
    op.drop_index('ix_wizard_session_tenant_project', table_name='wizard_session')
    op.drop_column('wizard_session', 'project_id')
