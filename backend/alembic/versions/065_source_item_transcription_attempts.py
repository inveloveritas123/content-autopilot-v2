"""source_items.transcription_attempts — Abbruchbedingung fuer batch_transcribe

Revision ID: 065
Revises: 064
Create Date: 2026-08-03

batch_transcribe zieht Items mit Status new/transcription_failed/needs_voicescriptor
und setzt bei Fehlschlag wieder transcription_failed. Der Endzustand ist damit zugleich
Eingangszustand — eine Endlosschleife per Konstruktion. Am 03.08.2026 liefen so 168
aussichtslose Podcast-Episoden alle 30 Minuten erneut und verbrannten das Ratenlimit,
an dem dann echte Nutzerarbeit starb.

Diese Spalte ist die fehlende Abbruchbedingung. Kein Backfill noetig — der
server_default gilt fuer den Bestand.

Ursprünglich Revision 058 in origin/main (Create Date 2026-08-03). Bei der
Highlander-Integration 2026-08-14 auf 065 umnummeriert, da 058 bereits durch
058_rls_tenant_isolation.py (feature/stufe2-produkt-Strang) belegt war —
unabhängige Tabellen, keine inhaltliche Kollision, reine Nummern-
Linearisierung ans Kettenende.
"""

import sqlalchemy as sa
from alembic import op

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_items",
        sa.Column(
            "transcription_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("source_items", "transcription_attempts")
