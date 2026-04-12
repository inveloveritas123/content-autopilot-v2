"""Add content_ideas, entrepreneur_answers, content_performances, idea_selection_logs tables.

Revision ID: 003
Revises: 002
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    # ═══ ContentIdea ═══
    op.create_table(
        "content_ideas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_item_id", UUID(as_uuid=True), sa.ForeignKey("source_items.id"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("angle", sa.String(50), default="meinung"),
        sa.Column("hook_suggestion", sa.Text, default=""),
        sa.Column("relevance_score", sa.Float, default=5.0),
        sa.Column("priority", sa.String(20), default="medium"),
        sa.Column("entrepreneur_questions", JSONB, server_default="[]"),
        sa.Column("source_quotes", JSONB, server_default="[]"),
        sa.Column("source_context", JSONB, server_default="{}"),
        sa.Column("status", sa.String(50), default="new"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_ideas_source_item", "content_ideas", ["source_item_id"])
    op.create_index("idx_ideas_tenant_status", "content_ideas", ["tenant_id", "status"])
    op.create_index("idx_ideas_angle", "content_ideas", ["angle"])

    # ═══ EntrepreneurAnswer ═══
    op.create_table(
        "entrepreneur_answers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("content_idea_id", UUID(as_uuid=True), sa.ForeignKey("content_ideas.id"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("question_index", sa.Integer, nullable=False),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("answer_text", sa.Text, nullable=False),
        sa.Column("answer_source", sa.String(50), default="web_ui"),
        sa.Column("voice_analysis", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_answers_idea", "entrepreneur_answers", ["content_idea_id"])
    op.create_index("idx_answers_tenant", "entrepreneur_answers", ["tenant_id"])

    # ═══ ContentPerformance ═══
    op.create_table(
        "content_performances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("content_piece_id", UUID(as_uuid=True), sa.ForeignKey("content_pieces.id"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("linkedin_post_id", sa.String(100)),
        sa.Column("impressions", sa.Integer),
        sa.Column("reactions", sa.Integer),
        sa.Column("comments", sa.Integer),
        sa.Column("shares", sa.Integer),
        sa.Column("clicks", sa.Integer),
        sa.Column("engagement_rate", sa.Float),
        sa.Column("was_selected", sa.Boolean, default=True),
        sa.Column("variant_index", sa.Integer),
        sa.Column("edit_diff", sa.Text),
        sa.Column("edit_distance", sa.Integer),
        sa.Column("was_published", sa.Boolean, default=False),
        sa.Column("angle", sa.String(50)),
        sa.Column("source_type", sa.String(50)),
        sa.Column("posted_at", sa.DateTime),
        sa.Column("day_of_week", sa.Integer),
        sa.Column("hour_of_day", sa.Integer),
        sa.Column("raw_data", JSONB, server_default="{}"),
        sa.Column("data_source", sa.String(50), default="manual"),
        sa.Column("measured_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_perf_content_piece", "content_performances", ["content_piece_id"])
    op.create_index("idx_perf_tenant_date", "content_performances", ["tenant_id", "measured_at"])

    # ═══ IdeaSelectionLog ═══
    op.create_table(
        "idea_selection_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("content_idea_id", UUID(as_uuid=True), sa.ForeignKey("content_ideas.id"), nullable=False),
        sa.Column("source_item_id", UUID(as_uuid=True), sa.ForeignKey("source_items.id"), nullable=False),
        sa.Column("total_ideas_shown", sa.Integer, default=0),
        sa.Column("was_selected", sa.Boolean, default=False),
        sa.Column("selection_order", sa.Integer),
        sa.Column("angle", sa.String(50)),
        sa.Column("relevance_score", sa.Float),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_selection_tenant", "idea_selection_logs", ["tenant_id"])
    op.create_index("idx_selection_idea", "idea_selection_logs", ["content_idea_id"])


def downgrade():
    op.drop_table("idea_selection_logs")
    op.drop_table("content_performances")
    op.drop_table("entrepreneur_answers")
    op.drop_table("content_ideas")
