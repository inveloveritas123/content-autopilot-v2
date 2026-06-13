# freigabe-robert: neue Tabelle — NICHT automatisch auf Prod anwenden.
"""Add tenant_customer_values (4. Profil-Entität, #43) + voice_drift_observation.entity_type.

Revision ID: 053
Revises: 049
Create Date: 2026-06-12

Issue #43: tenant_customer_values als vierter Zwilling der kanonischen Profil-Tabellen
(exakter 1:1-Zwilling von tenant_voice_profile/018, inkl. project_id + COALESCE-Unique-Index
aus Migration 032, source-CHECK mit 2 neuen Werten). Zusätzlich: entity_type-Spalte auf
voice_drift_observation für den entitäts-generischen P17-Schreibpfad (Schritt 4, #43).

KETTE: down_revision='049' (aktuell höchste echte Migration). Issue #26 reserviert 050–052,
ist aber noch NICHT gebaut. Wenn #26 VOR #43 mergt → 053.down_revision auf '052' bumpen
(oder `alembic merge`), damit kein doppelter Head entsteht. Vor dem Merge mit Robert abstimmen.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "053"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade():
    # 1. tenant_customer_values — exakter Zwilling von tenant_voice_profile (018:51-82)
    #    plus project_id-Parität (032:21-23/28-30) plus 2 neue source-Werte.
    op.create_table(
        "tenant_customer_values",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", UUID(as_uuid=False), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "source",
            sa.Text(),
            sa.CheckConstraint(
                "source IN ('transcript','md_upload','json_upload','nc_import',"
                "'wizard','manual_edit','drift_update','memory_promotion','p17_update')",
                name="ck_tenant_customer_values_source",
            ),
        ),
        sa.Column("source_meta", JSONB()),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("prompt_version_hash", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_by", sa.Text()),
    )

    op.create_index(
        "ix_tenant_customer_values_tenant_id",
        "tenant_customer_values",
        ["tenant_id"],
    )

    op.create_foreign_key(
        "fk_tcv_project_id",
        "tenant_customer_values",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # COALESCE-Form aus Migration 032 — von Tag 1 project_id-aware.
    op.execute(
        "CREATE UNIQUE INDEX uq_tenant_customer_values_active "
        "ON tenant_customer_values "
        "(tenant_id, COALESCE(project_id, '00000000-0000-0000-0000-000000000000')) "
        "WHERE is_active = true"
    )

    # 2. voice_drift_observation.entity_type — für den entitäts-generischen P17-Pfad (§5).
    #    server_default='voice' macht alle Bestands-Rows rückwärtskompatibel;
    #    bestehende Schreiber/Leser (voice_drift_task.py, brand_voice.py) funktionieren
    #    ohne Code-Änderung weiter (additive Spalte).
    op.add_column(
        "voice_drift_observation",
        sa.Column("entity_type", sa.Text(), nullable=False, server_default=sa.text("'voice'")),
    )
    op.create_check_constraint(
        "ck_voice_drift_observation_entity_type",
        "voice_drift_observation",
        "entity_type IN ('voice','values','avatar','context')",
    )


def downgrade():
    # 2. entity_type rückgängig
    op.drop_constraint(
        "ck_voice_drift_observation_entity_type",
        "voice_drift_observation",
        type_="check",
    )
    op.drop_column("voice_drift_observation", "entity_type")

    # 1. tenant_customer_values rückgängig (Reihenfolge: Index → FK → Tabelle, Muster 018:217-239)
    op.execute("DROP INDEX IF EXISTS uq_tenant_customer_values_active")
    op.drop_constraint("fk_tcv_project_id", "tenant_customer_values", type_="foreignkey")
    op.drop_index("ix_tenant_customer_values_tenant_id", table_name="tenant_customer_values")
    op.drop_table("tenant_customer_values")
