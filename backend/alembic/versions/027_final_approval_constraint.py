"""Final Approval Constraint — approval_method column

Revision ID: 027
Revises: 026
"""
from alembic import op
import sqlalchemy as sa

revision = '027'
down_revision = '026'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('content_pieces', sa.Column('approval_method', sa.String(50), nullable=True))


def downgrade():
    op.drop_column('content_pieces', 'approval_method')
