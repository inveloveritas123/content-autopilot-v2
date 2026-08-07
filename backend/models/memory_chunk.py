"""MemoryChunk — Unternehmensgedächtnis (Phase 5.1, Issue #140).

Vektorspeicher für unstrukturierte Inhalte: Sprachnotizen aus Telegram/
WhatsApp, Fotos mit OCR + Beschreibung, manuelle Notizen.

Tenant-isoliert. HNSW-Index für semantische Suche.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class MemoryChunk(Base):
    __tablename__ = "memory_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str | None] = mapped_column(String(20), nullable=True)
    chunk_metadata: Mapped[dict] = mapped_column(
        "metadata",  # SQL-Spalte heisst "metadata", Python-Attribut chunk_metadata um SQLAlchemy-Konflikt zu vermeiden
        JSONB,
        default=dict,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # embedding-Spalte: SQLAlchemy-fremder Vector-Type — wird via Raw-SQL geschrieben/gelesen.
    # Im ORM hier weglassen; Service-Layer arbeitet mit text() + bind-Params.

    tenant = relationship("Tenant")
