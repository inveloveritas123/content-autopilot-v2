"""Strukturiertes Onboarding-Profil pro Tenant.

Issue #148. Multi-Source: manual / md_upload / wizard / voice_extracted.
Provenance-Side-Table dient als Audit-Trail für DSGVO + Konflikt-Resolution.
"""
from __future__ import annotations

import datetime
import uuid
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


SOURCE_TRUST = {
    "manual_input": 1.0,
    "md_upload": 0.9,
    "wizard_explicit": 0.85,
    "auto_enrich": 0.8,
    "voice_extracted": 0.7,
    "wizard_inferred": 0.6,
    "legacy_migration": 0.5,
}

AUTO_APPLY_THRESHOLD = 0.85


class CompanyProfile(Base):
    __tablename__ = "company_profile"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contact_person_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    founded_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    headcount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    company_size: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    legal_form: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    usp: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_audience: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    values_short: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProfileFieldProvenance(Base):
    __tablename__ = "profile_field_provenance"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    conflict_with_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    applied_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
