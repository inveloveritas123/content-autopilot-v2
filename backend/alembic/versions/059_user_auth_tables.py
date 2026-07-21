"""User-/Agentur-/Auth-Tabellen (W3, 2026-07-21).

Revision ID: 059
Revises: 058
Create Date: 2026-07-21

Erzeugt die 4 Tabellen der Auth-/RBAC-Hierarchie aus models/user.py:

    Agency (Agentur, White-Label-Ebene)
      └── User (Login via Magic-Link, gehört zu genau EINER Agentur)
            └── verwaltet N Tenants (über user_tenant, mit Rollen-Scope)

Auth ist PASSWORTLOS (Magic-Link, siehe services/auth.py + models/user.py-Docstring):
`magic_link_tokens` speichert nur den SHA-256-Hash des Einmal-Tokens, nie den
Klartext. `users.password_hash` ist optional vorbereitet (Argon2, spätere
Agentur-Admins) — Magic-Link-Login braucht ihn nicht.

WICHTIG: Diese 4 Tabellen sind AUTH-Ebene (Agentur/User), NICHT tenant-scoped —
sie bekommen bewusst KEINE RLS-Policy (anders als die 41 Tenant-Tabellen aus
Migration 058). Zugriffskontrolle läuft hier über die Anwendungsschicht
(services/auth.py::user_may_access_tenant), nicht über Postgres-RLS.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agencies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True, index=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column(
            "agency_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agencies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(32), nullable=False, server_default="member"),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "user_tenant",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("scope", sa.String(32), nullable=False, server_default="own"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant"),
    )

    op.create_table(
        "magic_link_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("magic_link_tokens")
    op.drop_table("user_tenant")
    op.drop_table("users")
    op.drop_table("agencies")
