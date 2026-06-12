import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ContentDNAProfile(Base):
    __tablename__ = "content_dna_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    posts_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    voice_attributes: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    top_topics: Mapped[list | None] = mapped_column(JSONB, default=list)
    avg_engagement: Mapped[float | None] = mapped_column(Float)
    analysis_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, scraping, analyzing, done, error
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    tenant = relationship("Tenant")
    scraped_posts = relationship(
        "ScrapedPost", back_populates="dna_profile", cascade="all, delete-orphan"
    )


class ScrapedPost(Base):
    __tablename__ = "scraped_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dna_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_dna_profiles.id"), nullable=False
    )
    linkedin_post_id: Mapped[str | None] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int | None] = mapped_column(Integer)
    post_type: Mapped[str | None] = mapped_column(
        String(50)
    )  # text, image, video, carousel, article
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)
    hashtags: Mapped[list | None] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    dna_profile = relationship("ContentDNAProfile", back_populates="scraped_posts")
