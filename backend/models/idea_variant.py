"""IdeaVariant — 3 Aufhänger pro Idee (Phase 4.2, Issue #147)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class IdeaVariant(Base):
    __tablename__ = "idea_variants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    idea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_ideas.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_type: Mapped[str] = mapped_column(String(10), nullable=False)  # hook|story|these
    hook_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_outline: Mapped[str] = mapped_column(Text, nullable=False)
    is_chosen: Mapped[bool] = mapped_column(Boolean, default=False)
    chosen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    p12_run_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
