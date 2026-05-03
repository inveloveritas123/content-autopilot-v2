import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ContentPiece(Base):
    __tablename__ = "content_pieces"
    __table_args__ = (
        Index("idx_content_pieces_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("source_items.id"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    idea_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("content_ideas.id"), nullable=True)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime)
    approved_by: Mapped[Optional[str]] = mapped_column(String(100))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    approval_method: Mapped[Optional[str]] = mapped_column(String(50))  # web_ui / telegram_button / admin_override
    carousel_pdf_path: Mapped[Optional[str]] = mapped_column(String(500))
    category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # news/persoenlich/trust/praxis
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    source_item = relationship("SourceItem", back_populates="content_pieces")
    tenant = relationship("Tenant", back_populates="content_pieces")
    performances = relationship("ContentPerformance", back_populates="content_piece", cascade="all, delete-orphan")
