"""Add project_id to brand-voice tables and is_default to projects.

Revision ID: 032
Revises: 031
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '032'
down_revision = '031'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1 — Add is_default to projects
    op.add_column('projects', sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    # Step 2 — Add nullable project_id to brand-voice tables
    op.add_column('tenant_customer_context', sa.Column('project_id', UUID(as_uuid=False), nullable=True))
    op.add_column('tenant_voice_profile', sa.Column('project_id', UUID(as_uuid=False), nullable=True))
    op.add_column('tenant_audience_avatar', sa.Column('project_id', UUID(as_uuid=False), nullable=True))

    op.create_foreign_key(
        'fk_tcc_project_id', 'tenant_customer_context', 'projects', ['project_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_tvp_project_id', 'tenant_voice_profile', 'projects', ['project_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_taa_project_id', 'tenant_audience_avatar', 'projects', ['project_id'], ['id'], ondelete='SET NULL'
    )

    # Step 3 — Drop old unique partial indexes
    op.drop_index('uq_tenant_customer_context_active', table_name='tenant_customer_context')
    op.drop_index('uq_tenant_voice_profile_active', table_name='tenant_voice_profile')
    op.drop_index('uq_tenant_audience_avatar_active', table_name='tenant_audience_avatar')

    # Step 4 — Create new COALESCE-based unique partial indexes
    op.execute(
        "CREATE UNIQUE INDEX uq_tenant_customer_context_active "
        "ON tenant_customer_context (tenant_id, COALESCE(project_id, '00000000-0000-0000-0000-000000000000')) "
        "WHERE is_active = true"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_tenant_voice_profile_active "
        "ON tenant_voice_profile (tenant_id, COALESCE(project_id, '00000000-0000-0000-0000-000000000000')) "
        "WHERE is_active = true"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_tenant_audience_avatar_active "
        "ON tenant_audience_avatar (tenant_id, COALESCE(project_id, '00000000-0000-0000-0000-000000000000')) "
        "WHERE is_active = true"
    )


def downgrade():
    # Drop new COALESCE indexes
    op.execute("DROP INDEX IF EXISTS uq_tenant_customer_context_active")
    op.execute("DROP INDEX IF EXISTS uq_tenant_voice_profile_active")
    op.execute("DROP INDEX IF EXISTS uq_tenant_audience_avatar_active")

    # Restore old unique partial indexes
    op.execute(
        "CREATE UNIQUE INDEX uq_tenant_customer_context_active "
        "ON tenant_customer_context (tenant_id) WHERE is_active = true"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_tenant_voice_profile_active "
        "ON tenant_voice_profile (tenant_id) WHERE is_active = true"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_tenant_audience_avatar_active "
        "ON tenant_audience_avatar (tenant_id) WHERE is_active = true"
    )

    # Drop foreign keys
    op.drop_constraint('fk_tcc_project_id', 'tenant_customer_context', type_='foreignkey')
    op.drop_constraint('fk_tvp_project_id', 'tenant_voice_profile', type_='foreignkey')
    op.drop_constraint('fk_taa_project_id', 'tenant_audience_avatar', type_='foreignkey')

    # Drop project_id columns
    op.drop_column('tenant_customer_context', 'project_id')
    op.drop_column('tenant_voice_profile', 'project_id')
    op.drop_column('tenant_audience_avatar', 'project_id')

    # Drop is_default from projects
    op.drop_column('projects', 'is_default')
