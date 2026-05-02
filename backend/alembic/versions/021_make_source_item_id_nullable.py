"""make content_pieces.source_item_id nullable for P12 idea-based generation

Revision ID: 021
Revises: 020
Create Date: 2026-05-02
"""
from alembic import op

revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('content_pieces', 'source_item_id', nullable=True)


def downgrade():
    # Achtung: Wenn NULLs existieren, schlägt das fehl — manueller Schritt nötig
    op.alter_column('content_pieces', 'source_item_id', nullable=False)
