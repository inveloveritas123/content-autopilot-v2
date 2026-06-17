"""add onboarding mode to bot_session + onboarding source to tenant_voice_profile

Revision ID: 056
Revises: 055
Create Date: 2026-06-17
"""

from alembic import op

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. bot_session.mode: 'onboarding' hinzufügen
    op.execute("ALTER TABLE bot_session DROP CONSTRAINT IF EXISTS ck_bot_session_mode")
    op.execute(
        "ALTER TABLE bot_session ADD CONSTRAINT ck_bot_session_mode "
        "CHECK (mode IN ('targeted','random_smart','onboarding'))"
    )

    # 2. tenant_voice_profile.source: 'onboarding' hinzufügen
    op.execute(
        "ALTER TABLE tenant_voice_profile DROP CONSTRAINT IF EXISTS ck_tenant_voice_profile_source"
    )
    op.execute(
        "ALTER TABLE tenant_voice_profile ADD CONSTRAINT ck_tenant_voice_profile_source "
        "CHECK (source IN ('transcript','md_upload','json_upload','nc_import',"
        "'wizard','manual_edit','drift_update','voice_fallback','onboarding'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bot_session DROP CONSTRAINT IF EXISTS ck_bot_session_mode")
    op.execute(
        "ALTER TABLE bot_session ADD CONSTRAINT ck_bot_session_mode "
        "CHECK (mode IN ('targeted','random_smart'))"
    )

    op.execute(
        "ALTER TABLE tenant_voice_profile DROP CONSTRAINT IF EXISTS ck_tenant_voice_profile_source"
    )
    op.execute(
        "ALTER TABLE tenant_voice_profile ADD CONSTRAINT ck_tenant_voice_profile_source "
        "CHECK (source IN ('transcript','md_upload','json_upload','nc_import',"
        "'wizard','manual_edit','drift_update','voice_fallback'))"
    )
