"""
QualityMetric — Qualitäts-Tracking für jeden Pipeline-Schritt.

Wird automatisch nach jedem Schritt befüllt:
- completeness_score: regelbasiert (Länge, Tiefe)
- accuracy_score: LLM-basiert (optional, wenn Budget vorhanden)
- relevance_score: LLM-basiert (optional)

User-Feedback (user_rating, user_edited) wird vom Frontend gesetzt.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class QualityMetric(Base):
    __tablename__ = "quality_metrics"
    __table_args__ = (
        Index("idx_quality_metrics_item", "source_item_id"),
        Index("idx_quality_metrics_tenant_step", "tenant_id", "step"),
        Index("idx_quality_metrics_model", "model_used"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_items.id", ondelete="CASCADE")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    # Pipeline step
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    # transcription | analysis | ideation | post_generation | smart_questions

    # Model info
    model_used: Mapped[Optional[str]] = mapped_column(String(150))  # e.g. vertex/gemini-2.5-flash-lite

    # Token + cost data (from LLM call)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cost_cents: Mapped[Optional[float]] = mapped_column(Float)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Quality scores 0-100
    completeness_score: Mapped[Optional[float]] = mapped_column(Float)
    # Rule-based: transcript length vs expected, analysis field count, idea count
    accuracy_score: Mapped[Optional[float]] = mapped_column(Float)
    # LLM-based: coherence, factual plausibility (optional)
    relevance_score: Mapped[Optional[float]] = mapped_column(Float)
    # LLM-based: alignment with entrepreneur profile (optional)

    # Composite score (average of available scores)
    overall_score: Mapped[Optional[float]] = mapped_column(Float)

    # User feedback
    user_rating: Mapped[Optional[int]] = mapped_column(Integer)   # 1-5
    user_edited: Mapped[Optional[bool]] = mapped_column(Boolean)
    edit_distance: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
