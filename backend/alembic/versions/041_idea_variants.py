"""Phase 4.2 — idea_variants Tabelle (3 Aufhänger pro Idee)

Revision ID: 041
Revises: 040

Eric-Vorgabe: pro Idee 3 strukturell unterschiedliche Aufhänger:
  - hook   (provokant)
  - story  (persönlich)
  - these  (sachlich)

Tenant wählt vor der Finalisierung. Audit-Trail bleibt — alle 3
Varianten persistiert, auch nicht-gewählte (für spätere Voice-Drift-
Analyse: was hat der Tenant öfters gewählt?).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


VARIANT_TYPES = ("hook", "story", "these")


def upgrade() -> None:
    op.create_table(
        "idea_variants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("idea_id", UUID(as_uuid=True), sa.ForeignKey("content_ideas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_type", sa.String(10), nullable=False),
        sa.Column("hook_text", sa.Text, nullable=False),
        sa.Column("body_outline", sa.Text, nullable=False),
        sa.Column("is_chosen", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("chosen_at", sa.DateTime, nullable=True),
        sa.Column("p12_run_id", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    types_list = ", ".join(f"'{t}'" for t in VARIANT_TYPES)
    op.execute(
        f"ALTER TABLE idea_variants ADD CONSTRAINT ck_idea_variants_type "
        f"CHECK (variant_type IN ({types_list}))"
    )
    op.create_unique_constraint(
        "uq_idea_variants_idea_type", "idea_variants", ["idea_id", "variant_type"]
    )
    op.create_index("idx_idea_variants_idea_chosen", "idea_variants", ["idea_id", "is_chosen"])
    op.create_index("idx_idea_variants_tenant", "idea_variants", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_idea_variants_tenant", table_name="idea_variants")
    op.drop_index("idx_idea_variants_idea_chosen", table_name="idea_variants")
    op.drop_constraint("uq_idea_variants_idea_type", "idea_variants", type_="unique")
    op.drop_constraint("ck_idea_variants_type", "idea_variants", type_="check")
    op.drop_table("idea_variants")
