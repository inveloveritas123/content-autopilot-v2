"""Add carousel_pdf_path to content_pieces

Revision ID: 030
Revises: 029
"""
from alembic import op
import sqlalchemy as sa

revision = '030'
down_revision = '029'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('content_pieces', sa.Column('carousel_pdf_path', sa.String(500), nullable=True))


def downgrade():
    op.drop_column('content_pieces', 'carousel_pdf_path')
