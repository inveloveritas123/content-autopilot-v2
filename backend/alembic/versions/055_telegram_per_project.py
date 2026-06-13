"""Per-Projekt Telegram-Bot-Token + Status-Spalten in tenant_bot_config.

Revision ID: 055
Revises: 054
Create Date: 2026-06-13

Adds nine nullable columns to the existing `tenant_bot_config` table
(introduced in Migration 031) to support per-project Telegram bot tokens
managed by the platform:

- telegram_bot_token_encrypted  — Fernet-encrypted bot token
- telegram_bot_id               — numeric Telegram bot ID
- telegram_bot_username         — @username of the bot
- telegram_bot_status           — lifecycle state: 'active' | 'revoked' | 'error'
- telegram_validated_at         — timestamp of last successful /getMe call
- telegram_last_active_at       — timestamp of last processed update
- telegram_revoked_at           — timestamp when token was revoked
- telegram_last_error           — last error message from Telegram API
- telegram_poll_offset          — last processed getUpdates update_id

All columns are nullable; no backfill required.
"""

from alembic import op
import sqlalchemy as sa

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tenant_bot_config",
        sa.Column("telegram_bot_token_encrypted", sa.String(500), nullable=True),
    )
    op.add_column(
        "tenant_bot_config",
        sa.Column("telegram_bot_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "tenant_bot_config",
        sa.Column("telegram_bot_username", sa.Text(), nullable=True),
    )
    op.add_column(
        "tenant_bot_config",
        sa.Column("telegram_bot_status", sa.Text(), nullable=True),
    )
    op.add_column(
        "tenant_bot_config",
        sa.Column(
            "telegram_validated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tenant_bot_config",
        sa.Column(
            "telegram_last_active_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tenant_bot_config",
        sa.Column(
            "telegram_revoked_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tenant_bot_config",
        sa.Column("telegram_last_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "tenant_bot_config",
        sa.Column("telegram_poll_offset", sa.BigInteger(), nullable=True),
    )


def downgrade():
    # Remove in reverse addition order
    op.drop_column("tenant_bot_config", "telegram_poll_offset")
    op.drop_column("tenant_bot_config", "telegram_last_error")
    op.drop_column("tenant_bot_config", "telegram_revoked_at")
    op.drop_column("tenant_bot_config", "telegram_last_active_at")
    op.drop_column("tenant_bot_config", "telegram_validated_at")
    op.drop_column("tenant_bot_config", "telegram_bot_status")
    op.drop_column("tenant_bot_config", "telegram_bot_username")
    op.drop_column("tenant_bot_config", "telegram_bot_id")
    op.drop_column("tenant_bot_config", "telegram_bot_token_encrypted")
