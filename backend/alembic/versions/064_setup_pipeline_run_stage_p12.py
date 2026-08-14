"""widen setup_pipeline_run stage CHECK to cover p12/p12b/admin actions

Revision ID: 064
Revises: 063
Create Date: 2026-07-27

Der Constraint (Migration 018) kannte nur die Onboarding-Stages
('p01','p03','p04','md_convert','orchestrator'). p12/p12b (Interview→Post,
#19) sowie admin_override_publish/kill_switch (api/admin.py) wurden seither
eingeführt, ohne die Migration zu erweitern — jeder INSERT mit diesen Stages
scheiterte am CHECK-Constraint (IntegrityError), bevor der jeweilige Task
überhaupt einen LLM-Call absetzen konnte (#62 — Schritt-0-E2E-Test deckte das
live auf).

Ursprünglich Revision 057 in origin/main (Create Date 2026-07-27). Bei der
Highlander-Integration 2026-08-14 auf 064 umnummeriert, da 057 bereits durch
057_tenant_agentur_id.py (feature/stufe2-produkt-Strang) belegt war — beide
Migrationen betreffen unabhängige Tabellen, keine inhaltliche Kollision,
reine Nummern-Linearisierung ans Kettenende.
"""

from alembic import op

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None

_NEW_STAGES = (
    "'p01','p03','p04','md_convert','orchestrator',"
    "'p12','p12b','admin_override_publish','kill_switch'"
)
_OLD_STAGES = "'p01','p03','p04','md_convert','orchestrator'"


def upgrade() -> None:
    op.execute("ALTER TABLE setup_pipeline_run DROP CONSTRAINT IF EXISTS ck_setup_pipeline_run_stage")
    op.execute(
        "ALTER TABLE setup_pipeline_run ADD CONSTRAINT ck_setup_pipeline_run_stage "
        f"CHECK (stage IN ({_NEW_STAGES}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE setup_pipeline_run DROP CONSTRAINT IF EXISTS ck_setup_pipeline_run_stage")
    op.execute(
        "ALTER TABLE setup_pipeline_run ADD CONSTRAINT ck_setup_pipeline_run_stage "
        f"CHECK (stage IN ({_OLD_STAGES}))"
    )
