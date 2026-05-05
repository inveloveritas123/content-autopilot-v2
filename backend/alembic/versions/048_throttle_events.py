"""throttle_events — Audit-Log für Pipeline-Throttle-Trigger

Revision ID: 048
Revises: 047
Create Date: 2026-05-04

Issue #156: Pipeline-Pump-Throttle (Defense-in-Depth gegen Call-Anomalien).

- throttle_events: kein PII — nur Counts + Limit-Werte
- 90-Tage-Auto-Purge via Celery-Beat (cleanup_task)
- btree Index auf (tenant_id, created_at DESC) — kein Partial Index, da WHERE NOW() zur Erstellungszeit eingefroren wäre
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "throttle_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),          # 'tenant' | 'global'
        sa.Column("count_at_throttle", sa.Integer, nullable=False),
        sa.Column("limit_value", sa.Integer, nullable=False),
        sa.Column("task_name", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )

    # btree index on (tenant_id, created_at DESC) — no WHERE clause because a
    # partial index with NOW() is evaluated once at creation time and never
    # updated, making it dead after 7 days (M2 fix).
    op.create_index(
        "ix_throttle_events_tenant_created",
        "throttle_events",
        ["tenant_id", sa.text("created_at DESC")],
    )

    # Full-range index for 24h counter in admin endpoint
    op.create_index(
        "ix_throttle_events_created_at",
        "throttle_events",
        ["created_at"],
    )


def downgrade():
    op.drop_index("ix_throttle_events_created_at", table_name="throttle_events")
    op.drop_index("ix_throttle_events_tenant_created", table_name="throttle_events")
    op.drop_table("throttle_events")
