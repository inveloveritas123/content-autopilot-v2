"""widen setup_pipeline_run stage CHECK to cover p12/p12b/admin actions

Revision ID: 057
Revises: 056
Create Date: 2026-07-27

Der Constraint (Migration 018) kannte nur die Onboarding-Stages
('p01','p03','p04','md_convert','orchestrator'). p12/p12b (Interview→Post,
#19) sowie admin_override_publish/kill_switch (api/admin.py) wurden seither
eingeführt, ohne die Migration zu erweitern — jeder INSERT mit diesen Stages
scheiterte am CHECK-Constraint (IntegrityError), bevor der jeweilige Task
überhaupt einen LLM-Call absetzen konnte (#62 — Schritt-0-E2E-Test deckte das
live auf).
"""

from alembic import op

revision = "057"
down_revision = "056"
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
