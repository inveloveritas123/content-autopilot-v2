"""LLMTrace — Per-Call-Tracing für services/pipeline_llm.py (portiert aus Leitivo).

Zweck: pro ``call_pipeline_llm``-Aufruf eine schlanke Metrik-Zeile —
Modell/Tier, Tokens, Kosten, Latenz, Outcome. Kein Klartext (Prompt/Response
werden hier NICHT gespeichert, auch nicht gehasht — das Repo loggt ohnehin
keinen Klartext im Trace-Pfad, siehe services/pipeline_llm.py).

Abgrenzung zu ``llm_call_logs`` (models/llm_call_log.py):
- ``llm_call_logs`` ist das bestehende Tenant-Cost-Ledger (task_type-basiert,
  DB-Write explizit in den aufrufenden Tasks) — bleibt unverändert bestehen.
- ``llm_trace`` ist NEU und ausschließlich additiv: eine Best-Effort-Zeile,
  die ``call_pipeline_llm`` selbst nach jedem Call schreibt (siehe
  services/pipeline_llm.py::_record_trace_best_effort). Sie darf NIE den
  eigentlichen LLM-Call zum Scheitern bringen — Schreibfehler werden nur
  geloggt (try/except), niemals propagiert.

Tenant-scoped → RLS PFLICHT (Migration 061, analog Migration 058):
ENABLE + FORCE ROW LEVEL SECURITY, tenant_isolation-Policy.

Felder:
- tenant_id (uuid, FK tenants.id) — Tenant-Scope.
- prompt_key (varchar(50))        — z.B. "P01", "P12" (siehe pipeline_llm.MODEL_PER_PROMPT).
- model (varchar(100))            — Router-Modell-ID (z.B. "bedrock/claude-sonnet-4-6@eu-central-1").
- tier (varchar(10))               — Tier-Name (z.B. "S6").
- tokens_in / tokens_out (int)    — Tatsächliche Token-Counts aus der Response.
- cost_usd (float)                — Geschätzte Kosten (TIER_PRICING, ohne Cache-Rabatt).
- latency_ms (int)                — Wall-Clock zwischen Call-Start und Antwort/Fehler.
- status (varchar(20))            — ok | error | budget_exceeded | http_error | timeout.
- created_at (timestamptz)        — Server-Zeit.

Index: (tenant_id, created_at) — Aggregat-Query pro Tenant/Zeitraum.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LLMTrace(Base):
    """Append-only Per-Call-Tracing-Zeile für ``call_pipeline_llm``."""

    __tablename__ = "llm_trace"
    __table_args__ = (Index("idx_llm_trace_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    prompt_key: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    tier: Mapped[str] = mapped_column(String(10), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
