"""
DialogueQuestion — Smarte Fragen für den Dialogue-Workflow.

Generiert nach der Analyse eines Items, referenziert spezifische Transkript-Stellen.
Robert beantwortet diese Fragen in Claude Desktop — die Antworten fließen in die Post-Generierung.

Workflow: SourceItem.analyzed → DialogueQuestion(s) generated → answers collected → Post generated in Claude
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DialogueQuestion(Base):
    __tablename__ = "dialogue_questions"
    __table_args__ = (
        Index("idx_dialogue_questions_item", "source_item_id"),
        Index("idx_dialogue_questions_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_items.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )

    # Question content
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    transcript_reference: Mapped[str | None] = mapped_column(Text)  # Specific quote from transcript
    why_relevant: Mapped[str | None] = mapped_column(Text)  # Why this question matters
    target_angle: Mapped[str | None] = mapped_column(
        String(50)
    )  # story, opinion, how_to, controversy

    order_index: Mapped[int] = mapped_column(Integer, default=0)

    # Answer
    answer_text: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
