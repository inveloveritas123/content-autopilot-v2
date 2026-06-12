import datetime
import uuid

from sqlalchemy import Boolean, DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    api_key_secondary: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Phase 4.4 / #141 — Branchen-spezifisches Scoring
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())

    enabled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), nullable=False, default=True
    )
    disabled_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    disabled_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    disabled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    sources = relationship("Source", back_populates="tenant", cascade="all, delete-orphan")
    source_items = relationship("SourceItem", back_populates="tenant", cascade="all, delete-orphan")
    content_pieces = relationship(
        "ContentPiece", back_populates="tenant", cascade="all, delete-orphan"
    )
    campaigns = relationship("Campaign", back_populates="tenant", cascade="all, delete-orphan")
