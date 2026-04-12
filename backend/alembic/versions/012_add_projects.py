"""Add projects table and project_id to sources.

Revision ID: 012
Revises: 011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '012'
down_revision = '011'

def upgrade() -> None:
    # Create projects table
    op.create_table(
        'projects',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(500)),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Add project_id to sources (nullable for now, will backfill)
    op.add_column('sources', sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=True))

    # Create default project and assign existing sources
    # This is done in application startup (main.py), not here

def downgrade() -> None:
    op.drop_column('sources', 'project_id')
    op.drop_table('projects')
