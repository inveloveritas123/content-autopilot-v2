"""
EntrepreneurAnswer — Antworten des Unternehmers auf gezielte Fragen.

Diese Antworten sind der Kern des dialogischen Workflows:
- System generiert Fragen basierend auf ContentIdea
- Unternehmer antwortet per UI (spaeter: Messenger)
- Aus Antworten + Analyse wird authentischer Content generiert

Die Antworten werden NICHT direkt als Post-Text verwendet,
sondern fliessen als "echte Stimme" in die Content-Generierung ein.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class EntrepreneurAnswer(Base):
    __tablename__ = "entrepreneur_answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_idea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_ideas.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )

    # Frage-Referenz (Index in content_idea.entrepreneur_questions)
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # Kopie der Frage fuer Nachvollziehbarkeit

    # Antwort des Unternehmers
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_source: Mapped[str] = mapped_column(
        String(50), default="web_ui"
    )  # web_ui, whatsapp, telegram, voice

    # Optional: Sprachanalyse der Antwort (fuer Brand Voice Learning)
    voice_analysis: Mapped[dict | None] = mapped_column(JSONB)
    # Format: {"tone": "...", "vocabulary_level": "...", "sentence_length_avg": ..., "key_phrases": [...]}

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    content_idea = relationship("ContentIdea", back_populates="answers")
    tenant = relationship("Tenant", backref="entrepreneur_answers")
