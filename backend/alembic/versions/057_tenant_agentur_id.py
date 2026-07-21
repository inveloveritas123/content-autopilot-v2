"""Neue Spalte tenants.agentur_id für explizite Agentur-Zuordnung.

Revision ID: 057
Revises: 056
Create Date: 2026-06-14 (rebased 2026-07-21: 056→057, Kollision mit 056_bot_session_onboarding_mode aufgelöst)

Issue #26 — _meta-Rehydration Stufe iv.

Fügt eine eigene Spalte `agentur_id` zur `tenants`-Tabelle hinzu, damit
der Wert nicht mehr aus dem settings-JSONB-Blob gelesen werden muss.

- Nullable + server_default 'zb' → kein Backfill-Run nötig, bestehende Rows
  erhalten automatisch den korrekten Wert 'zb' via DB-Default.
- NOT-NULL-Kontrakt + historischer Hash-Backfill = Robert/DEFERIERT (separates ADR).
"""

import sqlalchemy as sa

from alembic import op

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "agentur_id",
            sa.Text(),
            nullable=True,
            server_default="zb",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "agentur_id")
