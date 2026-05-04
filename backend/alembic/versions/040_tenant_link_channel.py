"""Phase 5 follow-up: tenant_telegram_link.channel-Spalte

Revision ID: 040
Revises: 039

Multi-Channel-Support: gleicher Tenant kann sowohl Telegram als auch
WhatsApp verbunden haben. Bestehende Rows bekommen channel='telegram'
als Default (Backwards-Compat). Primary-Key auf
(tenant_id, telegram_user_id, channel) erweitert, damit der gleiche
User-Identifier in beiden Channels auftauchen kann.
"""
from alembic import op
import sqlalchemy as sa


revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Spalte mit Default 'telegram' (Backwards-Compat für bestehende Rows)
    op.add_column(
        "tenant_telegram_link",
        sa.Column("channel", sa.String(20), nullable=False, server_default="telegram"),
    )
    # 2) CHECK-Constraint auf erlaubte Channels
    op.create_check_constraint(
        "ck_tenant_telegram_link_channel",
        "tenant_telegram_link",
        "channel IN ('telegram', 'whatsapp')",
    )
    # 3) PK von (tenant_id, telegram_user_id) auf (tenant_id, telegram_user_id, channel) erweitern
    op.execute("ALTER TABLE tenant_telegram_link DROP CONSTRAINT IF EXISTS pk_tenant_telegram_link")
    op.create_primary_key(
        "pk_tenant_telegram_link",
        "tenant_telegram_link",
        ["tenant_id", "telegram_user_id", "channel"],
    )
    # 4) Lookup-Index auf (channel, telegram_user_id, status)
    op.create_index(
        "idx_tenant_telegram_link_channel_user",
        "tenant_telegram_link",
        ["channel", "telegram_user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_tenant_telegram_link_channel_user", table_name="tenant_telegram_link")
    op.execute("ALTER TABLE tenant_telegram_link DROP CONSTRAINT IF EXISTS pk_tenant_telegram_link")
    op.create_primary_key(
        "pk_tenant_telegram_link",
        "tenant_telegram_link",
        ["tenant_id", "telegram_user_id"],
    )
    op.drop_constraint("ck_tenant_telegram_link_channel", "tenant_telegram_link", type_="check")
    op.drop_column("tenant_telegram_link", "channel")
