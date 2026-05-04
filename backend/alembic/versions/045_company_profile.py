"""company_profile + profile_field_provenance

Revision ID: 045
Revises: 044
Create Date: 2026-05-03

Phase 8.x: Strukturiertes Onboarding-Profil (Issue #148, Großauftrag).

- company_profile: 1:1 mit tenants, ~15 Standard-Felder + JSONB extra
- profile_field_provenance: Audit-Trail (source/value/confidence/applied)
- Backfill: aus tenants.industry und settings.entrepreneur initialisieren
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("contact_person_name", sa.String(255), nullable=True),
        sa.Column("contact_role", sa.String(100), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("founded_year", sa.Integer(), nullable=True),
        sa.Column("headcount", sa.Integer(), nullable=True),
        sa.Column("company_size", sa.String(20), nullable=True),
        sa.Column("legal_form", sa.String(50), nullable=True),
        sa.Column("usp", sa.Text(), nullable=True),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column("values_short", sa.Text(), nullable=True),
        sa.Column("extra", postgresql.JSONB(), nullable=True,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_company_profile_tenant", "company_profile", ["tenant_id"])

    op.create_table(
        "profile_field_provenance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("conflict_with_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source IN ('manual_input','md_upload','wizard_explicit',"
            "'voice_extracted','wizard_inferred','auto_enrich','legacy_migration')",
            name="ck_provenance_source",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_provenance_confidence",
        ),
    )
    op.create_index("ix_provenance_tenant_field", "profile_field_provenance",
                    ["tenant_id", "field_name"])
    op.create_index("ix_provenance_pending", "profile_field_provenance",
                    ["tenant_id", "applied"],
                    postgresql_where=sa.text("applied = false"))

    op.execute("""
        INSERT INTO company_profile (tenant_id, company_name, industry)
        SELECT id, name, industry FROM tenants
        WHERE id NOT IN (SELECT tenant_id FROM company_profile)
    """)
    op.execute("""
        INSERT INTO profile_field_provenance
            (tenant_id, field_name, source, value, confidence, applied, applied_at)
        SELECT id, 'company_name', 'legacy_migration', name, 0.5, true, NOW()
        FROM tenants WHERE name IS NOT NULL
    """)
    op.execute("""
        INSERT INTO profile_field_provenance
            (tenant_id, field_name, source, value, confidence, applied, applied_at)
        SELECT id, 'industry', 'legacy_migration', industry, 0.5, true, NOW()
        FROM tenants WHERE industry IS NOT NULL AND industry != ''
    """)


def downgrade():
    op.drop_index("ix_provenance_pending", "profile_field_provenance")
    op.drop_index("ix_provenance_tenant_field", "profile_field_provenance")
    op.drop_table("profile_field_provenance")
    op.drop_index("ix_company_profile_tenant", "company_profile")
    op.drop_table("company_profile")
