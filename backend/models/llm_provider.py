import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class LLMProvider(Base):
    __tablename__ = "llm_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)  # openai, anthropic, google, litellm, local
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(String(500))
    base_url: Mapped[Optional[str]] = mapped_column(String(500))
    model_name: Mapped[Optional[str]] = mapped_column(String(100))
    task_assignment: Mapped[str] = mapped_column(String(50), default="all")  # analysis, creative, transcription, all
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    last_test_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_test_status: Mapped[Optional[str]] = mapped_column(String(20))  # ok, error
    last_test_error: Mapped[Optional[str]] = mapped_column(String(500))
    cost_limit_daily_cents: Mapped[int] = mapped_column(Integer, default=500, server_default="500")
    cost_spent_today_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    auto_cache: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant")
