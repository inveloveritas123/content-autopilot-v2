"""Extend ck_tenant_voice_profile_source to include 'voice_fallback' (#32 S2).

Revision ID: 054
Revises: 053
Create Date: 2026-06-13

P03-Fallback (p03_voice_fallback.py) writes source='voice_fallback' to tenant_voice_profile,
but the CHECK constraint from Migration 018 only allows the original 7 values.
This migration drops + recreates the constraint to add 'voice_fallback'.
"""


from alembic import op

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_tenant_voice_profile_source",
        "tenant_voice_profile",
        type_="check",
    )
    op.create_check_constraint(
        "ck_tenant_voice_profile_source",
        "tenant_voice_profile",
        "source IN ('transcript','md_upload','json_upload','nc_import',"
        "'wizard','manual_edit','drift_update','voice_fallback')",
    )


def downgrade():
    op.drop_constraint(
        "ck_tenant_voice_profile_source",
        "tenant_voice_profile",
        type_="check",
    )
    op.create_check_constraint(
        "ck_tenant_voice_profile_source",
        "tenant_voice_profile",
        "source IN ('transcript','md_upload','json_upload','nc_import',"
        "'wizard','manual_edit','drift_update')",
    )
