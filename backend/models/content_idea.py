"""
ContentIdea — Zwischenschritt zwischen Analyse und Post-Erstellung.

Jede Idee hat:
- Einen Angle (Meinung, How-To, Story, Kontroverse, Statistik)
- Einen LinkedIn-Relevanz-Score
- 2-3 gezielte Fragen an den Unternehmer
- Status-Tracking durch den Dialog-Workflow

Workflow: SourceItem.analysis → ContentIdea(s) → EntrepreneurAnswer(s) → ContentPiece
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ContentIdea(Base):
    __tablename__ = "content_ideas"
    __table_args__ = (
        Index("idx_content_ideas_status", "tenant_id", "status"),
        Index("idx_content_ideas_source", "source_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_items.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )

    # Idee-Kern
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    angle: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # meinung, howto, story, kontroverse, statistik, trend
    hook_suggestion: Mapped[str | None] = mapped_column(Text)

    # Bewertung
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-10, LinkedIn-Relevanz
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Sortierung

    # Fragen fuer den Unternehmer (als JSON-Array)
    # Format: [{"question": "...", "purpose": "...", "example_answer": "..."}]
    entrepreneur_questions: Mapped[list | None] = mapped_column(JSONB)

    # Quelldaten aus der Analyse
    source_quotes: Mapped[list | None] = mapped_column(JSONB)  # Zitate aus dem Transkript
    source_context: Mapped[dict | None] = mapped_column(JSONB)  # Zusaetzlicher Kontext

    # Status-Tracking
    # new → questions_sent → answers_received → content_generated → archived
    status: Mapped[str] = mapped_column(String(50), default="new")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    source_item = relationship("SourceItem", back_populates="content_ideas")
    tenant = relationship("Tenant", backref="content_ideas")
    answers = relationship(
        "EntrepreneurAnswer", back_populates="content_idea", cascade="all, delete-orphan"
    )
    selection_logs = relationship(
        "IdeaSelectionLog", back_populates="content_idea", cascade="all, delete-orphan"
    )
    content_pieces = relationship("ContentPiece", backref="content_idea")
