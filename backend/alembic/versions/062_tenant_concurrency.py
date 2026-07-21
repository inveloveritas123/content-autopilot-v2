"""tenant_concurrency — Bulkhead-Zähler pro Tenant (W5, 2026-07-21).

Zählt gleichzeitig laufende schwere Tasks je Tenant (services/bulkhead.py). Verhindert
Noisy-Neighbor: ein Tenant kann nicht den ganzen Worker-Pool belegen.

Tenant-scoped → RLS wie bei den 41 Tenant-Tabellen (Migration 058-Muster). Der
Bulkhead-Code setzt den RLS-Kontext über die Task-Session; Cross-Tenant-Zugriff nur
mit explizitem Bypass.

Revision ID: 062
Revises: 061
Create Date: 2026-07-21
"""

import sqlalchemy as sa

from alembic import op

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None

_RLS_CONDITION = (
    "("
    "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    " OR current_setting('app.rls_bypass', true) = 'on'"
    ")"
)


def upgrade() -> None:
    op.execute(
        sa.text(
            "CREATE TABLE tenant_concurrency ("
            "  tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,"
            "  active integer NOT NULL DEFAULT 0,"
            "  updated_at timestamptz NOT NULL DEFAULT now()"
            ")"
        )
    )
    op.execute(sa.text("ALTER TABLE tenant_concurrency ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE tenant_concurrency FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY tenant_isolation ON tenant_concurrency "
            f"USING ({_RLS_CONDITION}) WITH CHECK ({_RLS_CONDITION})"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON tenant_concurrency"))
    op.execute(sa.text("DROP TABLE IF EXISTS tenant_concurrency"))
