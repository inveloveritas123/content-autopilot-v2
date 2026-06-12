import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500))
    channel_id: Mapped[str | None] = mapped_column(String(100))
    language: Mapped[str] = mapped_column(String(10), default="de")
    polling_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    auto_process: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tenant = relationship("Tenant", back_populates="sources")
    project = relationship("Project", back_populates="sources")
    items = relationship("SourceItem", back_populates="source", cascade="all, delete-orphan")
