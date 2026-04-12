import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_external"),
        Index("idx_source_items_status", "tenant_id", "status"),
        Index("idx_source_items_external", "source_id", "external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    url: Mapped[Optional[str]] = mapped_column(String(500))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="new")
    description: Mapped[Optional[str]] = mapped_column(Text)
    view_count: Mapped[Optional[int]] = mapped_column(Integer)
    view_history: Mapped[Optional[dict]] = mapped_column(JSONB)  # {"2026-04-01T12:00": 1234, ...}
    keywords: Mapped[Optional[list]] = mapped_column(JSONB)
    channel_name: Mapped[Optional[str]] = mapped_column(String(255))
    audio_url: Mapped[Optional[str]] = mapped_column(String(500))
    content_type: Mapped[Optional[str]] = mapped_column(String(50))  # video, article, podcast
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    transcript_text: Mapped[Optional[str]] = mapped_column(Text)
    transcript_source: Mapped[Optional[str]] = mapped_column(String(50))
    analysis: Mapped[Optional[dict]] = mapped_column(JSONB)
    campaign_match_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    source = relationship("Source", back_populates="items")
    tenant = relationship("Tenant", back_populates="source_items")
    campaign_match = relationship("Campaign", back_populates="matched_items")
    content_pieces = relationship("ContentPiece", back_populates="source_item", cascade="all, delete-orphan")
    content_ideas = relationship("ContentIdea", back_populates="source_item", cascade="all, delete-orphan")
