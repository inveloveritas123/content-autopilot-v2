"""Neue Spalte tenants.agentur_id für explizite Agentur-Zuordnung.

Revision ID: 056
Revises: 055
Create Date: 2026-06-14

Issue #26 — _meta-Rehydration Stufe iv.

Fügt eine eigene Spalte `agentur_id` zur `tenants`-Tabelle hinzu, damit
der Wert nicht mehr aus dem settings-JSONB-Blob gelesen werden muss.

- Nullable + server_default 'zb' → kein Backfill-Run nötig, bestehende Rows
  erhalten automatisch den korrekten Wert 'zb' via DB-Default.
- NOT-NULL-Kontrakt + historischer Hash-Backfill = Robert/DEFERIERT (separates ADR).
"""

from alembic import op
import sqlalchemy as sa

revision = "056"
down_revision = "055"
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
