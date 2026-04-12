"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tenants
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("api_key", sa.String(64), unique=True, nullable=False),
        sa.Column("settings", JSONB, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Sources
    op.create_table(
        "sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("channel_id", sa.String(100)),
        sa.Column("language", sa.String(10), server_default="de"),
        sa.Column("polling_interval_minutes", sa.Integer, server_default="15"),
        sa.Column("auto_process", sa.Boolean, server_default="false"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("last_checked_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Campaigns
    op.create_table(
        "campaigns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("keywords", JSONB, server_default=sa.text("'[]'")),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("nextcloud_folder", sa.String(500)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Source Items
    op.create_table(
        "source_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("url", sa.String(500)),
        sa.Column("published_at", sa.DateTime),
        sa.Column("duration_seconds", sa.Integer),
        sa.Column("thumbnail_url", sa.String(500)),
        sa.Column("status", sa.String(50), server_default="new"),
        sa.Column("transcript_text", sa.Text),
        sa.Column("transcript_source", sa.String(50)),
        sa.Column("analysis", JSONB),
        sa.Column("campaign_match_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("source_id", "external_id", name="uq_source_external"),
    )
    op.create_index("idx_source_items_status", "source_items", ["tenant_id", "status"])
    op.create_index("idx_source_items_external", "source_items", ["source_id", "external_id"])

    # Content Pieces
    op.create_table(
        "content_pieces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_item_id", UUID(as_uuid=True), sa.ForeignKey("source_items.id"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("content_text", sa.Text, nullable=False),
        sa.Column("content_metadata", JSONB, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("scheduled_for", sa.DateTime),
        sa.Column("approved_by", sa.String(100)),
        sa.Column("approved_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_content_pieces_status", "content_pieces", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_table("content_pieces")
    op.drop_table("source_items")
    op.drop_table("campaigns")
    op.drop_table("sources")
    op.drop_table("tenants")
