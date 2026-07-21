"""User-/Agentur-/Auth-Datenmodell (W3, 2026-07-21).

Hierarchie (aus Scope-Call mit Louis, E9 White-Label-Ziel):

    Agency (Agentur, White-Label-Ebene)
      └── User (Login via Magic-Link, gehört zu genau EINER Agentur)
            └── verwaltet N Tenants (über user_tenant, mit Rollen-Scope)

Auth ist PASSWORTLOS (Magic-Link, „Kleinkind-Test" — Endkunden merken sich nichts):
Der User gibt seine E-Mail ein, bekommt einen Einmal-Link, klickt, ist eingeloggt.
Optionale Agentur-Admins können später ein echtes Passwort bekommen (Argon2, portiert
aus LunaDeva) — Feld dafür vorbereitet, aber nicht Magic-Link-Pflicht.

RBAC: Rolle pro (User, Tenant) mit Scope-Semantik (aus Leitivo permission_utils):
- 'owner'   : Agentur-Eigner — alle Tenants der Agentur.
- 'manager' : verwaltet zugewiesene Tenants der Agentur.
- 'member'  : nur eigene/zugewiesene Tenants (der typische Endkunde).
"""

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Agency(Base):
    """White-Label-Agentur — Dach über Usern und Tenants (Stufe-3-ready)."""

    __tablename__ = "agencies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Branding-Overrides (Stufe 3 White-Label) — vorbereitet, JSONB-frei gehalten bis dahin.
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    users = relationship("User", back_populates="agency", cascade="all, delete-orphan")


class User(Base):
    """Login-Konto. Passwortloser Magic-Link-Login; Passwort optional (Agentur-Admins)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False
    )
    # Agentur-weite Rolle (owner/manager/member). Tenant-Feinscope via user_tenant.
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")
    # Optionaler Passwort-Hash (Argon2) für Agentur-Admins — Magic-Link braucht ihn NICHT.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    agency = relationship("Agency", back_populates="users")


class UserTenant(Base):
    """Welcher User welchen Tenant verwalten darf (+ Rollen-Scope pro Tenant)."""

    __tablename__ = "user_tenant"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Scope für diesen konkreten Tenant: 'own' (nur dieser) / 'agency' (alle der Agentur).
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="own")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MagicLinkToken(Base):
    """Kurzlebiger Einmal-Token für passwortlosen Login.

    Gespeichert wird nur der SHA-256-HASH des Tokens (nie der Klartext) — analog zu
    LunaDevas Refresh-Token-Muster. `used_at` verhindert Mehrfach-Einlösung.
    """

    __tablename__ = "magic_link_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
