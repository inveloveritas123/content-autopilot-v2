"""
ContentPerformance — Tracking von Post-Performance und implizitem Feedback.

Drei Feedback-Quellen:
1. Implizit: Ideen-Selektion, Varianten-Wahl, Edit-Diffs
2. Manuell: Unternehmer gibt Impressions/Reactions nach 48h ein
3. Automatisch: LinkedIn API (Phase 4)
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ContentPerformance(Base):
    """Tracking der Post-Performance auf LinkedIn + implizites Feedback."""

    __tablename__ = "content_performances"
    __table_args__ = (
        Index("idx_perf_content_piece", "content_piece_id"),
        Index("idx_perf_tenant_date", "tenant_id", "measured_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_piece_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_pieces.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )

    # LinkedIn-Metriken (manuell oder via API)
    linkedin_post_id: Mapped[str | None] = mapped_column(String(100))
    impressions: Mapped[int | None] = mapped_column(Integer)
    reactions: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    clicks: Mapped[int | None] = mapped_column(Integer)
    engagement_rate: Mapped[float | None] = mapped_column(Float)

    # Implizites Feedback
    was_selected: Mapped[bool] = mapped_column(
        Boolean, default=True
    )  # Wurde diese Variante gewählt?
    variant_index: Mapped[int | None] = mapped_column(Integer)  # Welche Variante (0, 1, 2)?
    edit_diff: Mapped[str | None] = mapped_column(Text)  # unified diff: generated vs final
    edit_distance: Mapped[int | None] = mapped_column(Integer)  # Levenshtein-Distanz
    was_published: Mapped[bool] = mapped_column(Boolean, default=False)

    # Kontext für Korrelations-Engine
    angle: Mapped[str | None] = mapped_column(String(50))  # meinung, howto, story, etc.
    source_type: Mapped[str | None] = mapped_column(String(50))  # youtube, rss, podcast
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)  # Wann auf LinkedIn gepostet
    day_of_week: Mapped[int | None] = mapped_column(Integer)  # 0=Mo, 6=So
    hour_of_day: Mapped[int | None] = mapped_column(Integer)  # 0-23

    # Erweiterte Daten
    raw_data: Mapped[dict | None] = mapped_column(JSONB, default=dict)  # Rohdaten von LinkedIn API

    # Tracking-Quelle
    data_source: Mapped[str] = mapped_column(
        String(50), default="manual"
    )  # manual, linkedin_api, inferred

    measured_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    content_piece = relationship("ContentPiece", back_populates="performances")
    tenant = relationship("Tenant")


class IdeaSelectionLog(Base):
    """Tracking welche Ideen der Unternehmer auswählt/ignoriert."""

    __tablename__ = "idea_selection_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    content_idea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_ideas.id"), nullable=False
    )
    source_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_items.id"), nullable=False
    )

    # Kontext
    total_ideas_shown: Mapped[int] = mapped_column(
        Integer, default=0
    )  # Wie viele Ideen waren verfügbar?
    was_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    selection_order: Mapped[int | None] = mapped_column(Integer)  # In welcher Reihenfolge gewählt?
    angle: Mapped[str | None] = mapped_column(String(50))
    relevance_score: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    content_idea = relationship("ContentIdea", back_populates="selection_logs")
    source_item = relationship("SourceItem")
