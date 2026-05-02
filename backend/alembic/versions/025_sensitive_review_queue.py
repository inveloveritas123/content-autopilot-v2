"""tenant_review_queue for sensitive posts

Revision ID: 025
Revises: 024
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('tenant_review_queue',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(100), nullable=False),
        sa.Column('content_piece_id', sa.String(36), nullable=True),
        sa.Column('post_text', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(20), server_default='medium'),  # low/medium/high
        sa.Column('categories', JSONB()),  # list of category strings
        sa.Column('flagged_phrases', JSONB()),  # list of {phrase, category}
        sa.Column('confidence', sa.Numeric(3, 2)),
        sa.Column('detection_layer', sa.String(10)),  # 'pattern' or 'llm'
        sa.Column('status', sa.String(20), server_default='pending'),  # pending/approved/rejected
        sa.Column('reviewed_by', sa.String(100)),
        sa.Column('review_note', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('reviewed_at', sa.DateTime()),
    )
    op.create_index('ix_review_queue_tenant_status', 'tenant_review_queue', ['tenant_id', 'status'])


def downgrade():
    op.drop_index('ix_review_queue_tenant_status', table_name='tenant_review_queue')
    op.drop_table('tenant_review_queue')
