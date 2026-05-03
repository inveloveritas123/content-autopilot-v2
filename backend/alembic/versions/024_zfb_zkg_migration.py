"""ZFB→ZKG tenant rename + test voice data cleanup + secondary API key support

Revision ID: 024
Revises: 023
"""
from alembic import op
import sqlalchemy as sa

revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add api_key_secondary column (required before the UPDATE below writes into it)
    op.add_column('tenants', sa.Column('api_key_secondary', sa.String(64), nullable=True))

    # 2. Delete test voice data for ZFB tenant BEFORE renaming the api_key
    #    (all data before real onboarding is test/dummy — no backup needed per spec)
    #    Subquery resolves while api_key is still '***REMOVED-TENANT-KEY***'
    op.execute("""
        DELETE FROM tenant_voice_profile
        WHERE tenant_id IN (SELECT id::text FROM tenants WHERE api_key = '***REMOVED-TENANT-KEY***' OR api_key = '***REMOVED-TENANT-KEY-ZKG***')
    """)
    op.execute("""
        DELETE FROM tenant_customer_context
        WHERE tenant_id IN (SELECT id::text FROM tenants WHERE api_key = '***REMOVED-TENANT-KEY***' OR api_key = '***REMOVED-TENANT-KEY-ZKG***')
    """)
    op.execute("""
        DELETE FROM tenant_audience_avatar
        WHERE tenant_id IN (SELECT id::text FROM tenants WHERE api_key = '***REMOVED-TENANT-KEY***' OR api_key = '***REMOVED-TENANT-KEY-ZKG***')
    """)

    # 3. Clear voice_profile_id refs in content_pieces (profiles are now gone)
    op.execute("""
        UPDATE content_pieces
        SET content_metadata = content_metadata - 'voice_profile_id'
        WHERE content_metadata ? 'voice_profile_id'
    """)

    # 4. Rename ZFB tenant → ZKG; keep old key as secondary for 3-month transition
    op.execute("""
        UPDATE tenants
        SET
            name = 'ZKG',
            api_key_secondary = api_key,
            api_key = '***REMOVED-TENANT-KEY-ZKG***'
        WHERE api_key = '***REMOVED-TENANT-KEY***'
    """)

    # 5. Create unique index on secondary key
    op.create_index('ix_tenants_api_key_secondary', 'tenants', ['api_key_secondary'], unique=True)


def downgrade():
    # NOTE: PARTIAL DOWNGRADE ONLY
    # Voice data deleted in upgrade() is NOT restored — it was test data, intentionally discarded.
    # This downgrade only restores the tenant name and API key rename.
    # Restore ZFB tenant (best effort)
    op.execute("""
        UPDATE tenants
        SET
            api_key = api_key_secondary,
            api_key_secondary = NULL,
            name = 'ZFB'
        WHERE api_key = '***REMOVED-TENANT-KEY-ZKG***'
    """)
    op.drop_index('ix_tenants_api_key_secondary', table_name='tenants')
    op.drop_column('tenants', 'api_key_secondary')
