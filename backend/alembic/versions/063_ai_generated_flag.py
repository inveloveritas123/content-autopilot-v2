"""content_pieces.ai_generated + human_reviewed — EU-AI-Act Art. 50 (W6, 2026-07-21).

Kennzeichnet KI-generierte Posts. ai_generated default true (jeder generierte Post
ist KI), human_reviewed default false (wird bei Kunden-Freigabe true). Nachweis der
KI-Herkunft bleibt dokumentiert; das manuelle Publishing (Kunde kopiert/postet) ist
die menschliche Autorisierung.

Revision ID: 063
Revises: 062
Create Date: 2026-07-21
"""

import sqlalchemy as sa

from alembic import op

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_pieces",
        sa.Column(
            "ai_generated", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
    )
    op.add_column(
        "content_pieces",
        sa.Column(
            "human_reviewed", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )


def downgrade() -> None:
    op.drop_column("content_pieces", "human_reviewed")
    op.drop_column("content_pieces", "ai_generated")
