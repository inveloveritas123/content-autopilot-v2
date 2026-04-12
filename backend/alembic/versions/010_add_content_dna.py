"""Add content_dna_profiles and scraped_posts tables.

Revision ID: 010
Revises: 009
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '010'
down_revision = '009'

def upgrade() -> None:
    op.create_table(
        'content_dna_profiles',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('linkedin_url', sa.String(500)),
        sa.Column('posts_analyzed', sa.Integer(), server_default='0'),
        sa.Column('voice_attributes', JSONB, server_default='{}'),
        sa.Column('top_topics', JSONB, server_default='[]'),
        sa.Column('avg_engagement', sa.Float()),
        sa.Column('analysis_status', sa.String(20), server_default='pending'),
        sa.Column('error_message', sa.String(500)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'scraped_posts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('dna_profile_id', UUID(as_uuid=True), sa.ForeignKey('content_dna_profiles.id'), nullable=False),
        sa.Column('linkedin_post_id', sa.String(100)),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('likes', sa.Integer(), server_default='0'),
        sa.Column('comments', sa.Integer(), server_default='0'),
        sa.Column('shares', sa.Integer(), server_default='0'),
        sa.Column('impressions', sa.Integer()),
        sa.Column('post_type', sa.String(50)),
        sa.Column('posted_at', sa.DateTime()),
        sa.Column('hashtags', JSONB, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

def downgrade() -> None:
    op.drop_table('scraped_posts')
    op.drop_table('content_dna_profiles')
