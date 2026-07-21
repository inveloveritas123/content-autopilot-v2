"""llm_trace — Per-Call-LLM-Tracing-Tabelle (portiert aus Leitivo, LLM-Observability).

Revision ID: 061
Revises: 060
Create Date: 2026-07-21

Kontext: services/pipeline_llm.py::call_pipeline_llm schreibt ab jetzt
best-effort eine Metrik-Zeile pro Call in ``llm_trace`` — Modell/Tier,
Tokens, Kosten, Latenz, Outcome. Kein Klartext (Prompt/Response werden hier
NICHT gespeichert, auch nicht gehasht — siehe models/llm_trace.py).

Tenant-scoped → RLS PFLICHT (analog Migration 058 rls_tenant_isolation):
ENABLE + FORCE ROW LEVEL SECURITY, tenant_isolation-Policy mit
NULLIF(current_setting('app.tenant_id', true), '')::uuid Fail-Closed-Match
ODER explizitem Cross-Tenant-Bypass (app.rls_bypass = 'on').

Index (tenant_id, created_at) für Aggregat-Queries pro Tenant/Zeitraum.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None

_TABLE = "llm_trace"

# Identisch zur RLS-Bedingung aus Migration 058: Zugriff ist erlaubt, wenn die
# Zeilen-tenant_id dem Session-Tenant entspricht ODER der explizite
# Cross-Tenant-Bypass gesetzt ist (services.rls.set_rls_bypass).
_RLS_CONDITION = (
    "("
    "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    " OR current_setting('app.rls_bypass', true) = 'on'"
    ")"
)


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prompt_key", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("tier", sa.String(10), nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_llm_trace_tenant_created", _TABLE, ["tenant_id", "created_at"])

    # RLS: Tenant-Isolation ist Pflicht für jede tenant-scoped Tabelle.
    op.execute(sa.text(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY tenant_isolation ON {_TABLE} "
            f"USING ({_RLS_CONDITION}) "
            f"WITH CHECK ({_RLS_CONDITION})"
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {_TABLE}"))
    op.execute(sa.text(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY"))
    op.drop_index("idx_llm_trace_tenant_created", table_name=_TABLE)
    op.drop_table(_TABLE)
