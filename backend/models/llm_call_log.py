import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_providers.id")
    )
    task_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # research, analysis, ideation, voice_profile, post_draft, post_finalize, content_dna, transcription
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_cents: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(default=True)
    error_message: Mapped[str | None] = mapped_column(String(500))
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
