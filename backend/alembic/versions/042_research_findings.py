"""Phase 6.1 — research_findings (P07 Themen-Research)

Revision ID: 042
Revises: 041

Tabelle für autonome Research-Befunde mit Hook-Vorschlägen pro Tenant.
Gespeist 2× pro Woche via tasks/p07_research_task.

Source-traceable: jeder Befund verweist auf source_item_id (FK) — kein
synthesis ohne nachweisbare Quelle (Master-MD Constraint).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


CATEGORIES = (
    "rules_constraints",       # Regulierung, Compliance
    "demand_behavior",         # Kundenwünsche, Marktnachfrage
    "tools_methods",           # Neue Werkzeuge / Prozesse
    "competition_market",      # Wettbewerber, M&A
    "costs_resources",         # Kosten, Ressourcen, Materialien
    "emerging_topics",         # Aktuell viel diskutierte Themen
)
IMPACT_RATINGS = ("positive", "neutral", "negative")


def upgrade() -> None:
    op.create_table(
        "research_findings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_item_id", UUID(as_uuid=True), sa.ForeignKey("source_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("source_publisher", sa.String(200), nullable=True),
        sa.Column("source_date", sa.DateTime, nullable=True),
        sa.Column("impact_rating", sa.String(10), nullable=False, server_default="neutral"),
        sa.Column("impact_justification", sa.Text, nullable=True),
        sa.Column("hooks", JSONB, server_default=sa.text("'[]'::jsonb")),  # ["Hook 1", "Hook 2", "Hook 3"]
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("dismissed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    cat_list = ", ".join(f"'{c}'" for c in CATEGORIES)
    op.execute(
        f"ALTER TABLE research_findings ADD CONSTRAINT ck_research_findings_category "
        f"CHECK (category IN ({cat_list}))"
    )
    impact_list = ", ".join(f"'{i}'" for i in IMPACT_RATINGS)
    op.execute(
        f"ALTER TABLE research_findings ADD CONSTRAINT ck_research_findings_impact "
        f"CHECK (impact_rating IN ({impact_list}))"
    )
    op.execute(
        "ALTER TABLE research_findings ADD CONSTRAINT ck_research_findings_status "
        "CHECK (status IN ('active', 'dismissed', 'used'))"
    )
    op.create_index("idx_research_findings_tenant_status", "research_findings", ["tenant_id", "status"])
    op.create_index("idx_research_findings_tenant_created", "research_findings", ["tenant_id", "created_at"])
    op.create_index("idx_research_findings_category", "research_findings", ["tenant_id", "category"])


def downgrade() -> None:
    op.drop_index("idx_research_findings_category", table_name="research_findings")
    op.drop_index("idx_research_findings_tenant_created", table_name="research_findings")
    op.drop_index("idx_research_findings_tenant_status", table_name="research_findings")
    op.drop_table("research_findings")
