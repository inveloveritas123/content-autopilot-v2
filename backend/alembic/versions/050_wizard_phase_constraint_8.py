"""Wizard current_phase constraint 6→8 (Issue #44)

Revision ID: 050
Revises: 049
Create Date: 2026-06-13
"""

from alembic import op

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_wizard_session_current_phase", "wizard_session", type_="check")
    op.create_check_constraint(
        "ck_wizard_session_current_phase",
        "wizard_session",
        "current_phase >= 1 AND current_phase <= 8",
    )


def downgrade() -> None:
    op.drop_constraint("ck_wizard_session_current_phase", "wizard_session", type_="check")
    op.create_check_constraint(
        "ck_wizard_session_current_phase",
        "wizard_session",
        "current_phase >= 1 AND current_phase <= 6",
    )
