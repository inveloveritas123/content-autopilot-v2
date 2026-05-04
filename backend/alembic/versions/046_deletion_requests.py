"""deletion_requests + soft-delete-columns für DSGVO Art. 17

Revision ID: 046
Revises: 045
Create Date: 2026-05-03

Issue #148, Welle E: Right-to-be-forgotten.

- deletion_requests: Audit-Log (10 Jahre Aufbewahrung)
- deleted_at-Spalten auf 4 tenant-scoped Tabellen für Soft-Delete
- 30-Tage-Cooldown via recovery_until
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "deletion_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # tenant_id absichtlich OHNE FK-Constraint auf tenants.id:
        # Das Audit-Log muss 10 Jahre aufbewahrt werden (DSGVO Art. 5 Abs. 2),
        # auch nachdem ein Tenant gelöscht wurde. Ein ON DELETE CASCADE würde
        # den Audit-Trail vernichten — das ist unzulässig.
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_name_snapshot", sa.String(255), nullable=True),
        sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("payload_filter", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("affected_records", postgresql.JSONB(), nullable=True),
        sa.Column("requested_by", sa.String(100), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("recovery_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("soft_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hard_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "mode IN ('full','memory_selective','telegram_purge','audit_selective')",
            name="ck_deletion_mode",
        ),
        sa.CheckConstraint(
            "status IN ('pending','soft_deleted','hard_deleted','recovered','expired','rejected')",
            name="ck_deletion_status",
        ),
    )
    op.create_index("ix_deletion_tenant", "deletion_requests", ["tenant_id"])
    op.create_index("ix_deletion_recovery", "deletion_requests",
                    ["status", "recovery_until"])

    op.add_column("memory_chunks", sa.Column(
        "deleted_at", sa.DateTime(timezone=True), nullable=True
    ))
    op.create_index("ix_memory_chunks_deleted",
                    "memory_chunks",
                    ["tenant_id", "deleted_at"],
                    postgresql_where=sa.text("deleted_at IS NOT NULL"))

    op.add_column("content_pieces", sa.Column(
        "deleted_at", sa.DateTime(timezone=True), nullable=True
    ))
    op.add_column("content_ideas", sa.Column(
        "deleted_at", sa.DateTime(timezone=True), nullable=True
    ))
    op.add_column("source_items", sa.Column(
        "deleted_at", sa.DateTime(timezone=True), nullable=True
    ))


def downgrade():
    op.drop_column("source_items", "deleted_at")
    op.drop_column("content_ideas", "deleted_at")
    op.drop_column("content_pieces", "deleted_at")
    op.drop_index("ix_memory_chunks_deleted", "memory_chunks")
    op.drop_column("memory_chunks", "deleted_at")
    op.drop_index("ix_deletion_recovery", "deletion_requests")
    op.drop_index("ix_deletion_tenant", "deletion_requests")
    op.drop_table("deletion_requests")
