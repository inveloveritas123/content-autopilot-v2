"""deletion_request_id FK auf Soft-Delete-Tabellen + llm_call_logs Cascade

Revision ID: 047
Revises: 046
Create Date: 2026-05-04

Issue #148, Welle E — Critical Fixes:
- Ersetzt BETWEEN ±2s Window durch expliziten FK (Critical #2)
- Erweitert Cascade auf llm_call_logs (Critical #4)
- M5: telegram_message_log bekommt deleted_at + deletion_request_id —
  damit ist telegram_purge vollständig recoverable (DSGVO-Recovery-Versprechen).
- Backfill: BEST-EFFORT per ±5min Heuristik; nicht-eindeutige Rows bleiben
  NULL und werden durch Hard-Delete-Cron irgendwann bereinigt.

Hinweis zu transcripts: Die transcripts-Tabelle existiert nicht als
eigenständige Tabelle. Transkripte sind als Spalte in source_items bzw.
memory_chunks gespeichert und sind über die Cascade dieser Tabellen
bereits abgedeckt.

Hinweis zu deletion_requests.tenant_id: FK absichtlich ohne Kaskade —
10-Jahres-Audit-Log muss nach Tenant-Delete bestehen bleiben (DSGVO Art. 5
Abs. 2). Vgl. Migration 046.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None

# Tabellen die deletion_request_id bekommen (Soft-Delete-Kandidaten)
_SOFT_DELETE_TABLES = (
    "memory_chunks",
    "content_pieces",
    "content_ideas",
    "source_items",
    "llm_call_logs",
)


def upgrade():
    for table in _SOFT_DELETE_TABLES:
        op.add_column(
            table,
            sa.Column(
                "deletion_request_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("deletion_requests.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(
            f"idx_{table}_deletion_request_id",
            table,
            ["deletion_request_id"],
            postgresql_where=sa.text("deletion_request_id IS NOT NULL"),
        )

    # BEST-EFFORT Backfill: ordnet vorhandene Soft-Delete-Rows dem zeitlich
    # nächstgelegenen deletion_request zu (±5min Fenster).
    # Nicht-eindeutige Rows (kein passender Request) bleiben NULL.
    for table in _SOFT_DELETE_TABLES:
        if table == "llm_call_logs":
            # llm_call_logs hat kein deleted_at in der Basis-Migration —
            # wird durch deleted_at-Spalte ergänzt falls gesetzt; skip Backfill
            continue
        op.execute(sa.text(f"""
            UPDATE {table} t
            SET deletion_request_id = (
                SELECT dr.id
                FROM deletion_requests dr
                WHERE dr.tenant_id = t.tenant_id
                  AND dr.soft_deleted_at IS NOT NULL
                  AND t.deleted_at BETWEEN
                        dr.soft_deleted_at - INTERVAL '5 minutes'
                    AND dr.soft_deleted_at + INTERVAL '5 minutes'
                ORDER BY ABS(EXTRACT(EPOCH FROM (t.deleted_at - dr.soft_deleted_at))) ASC
                LIMIT 1
            )
            WHERE t.deleted_at IS NOT NULL
              AND t.deletion_request_id IS NULL
        """))

    # deleted_at für llm_call_logs hinzufügen (Soft-Delete-Unterstützung)
    op.add_column(
        "llm_call_logs",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_llm_call_logs_deleted",
        "llm_call_logs",
        ["tenant_id", "deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )

    # M5: telegram_message_log — deleted_at + deletion_request_id für Recovery-Symmetrie.
    # Ohne diese Spalten wäre telegram_purge ein one-way soft-delete ohne Recovery-Möglichkeit,
    # was das DSGVO-Recovery-Versprechen (30 Tage) für telegram_purge bricht.
    op.add_column(
        "telegram_message_log",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "telegram_message_log",
        sa.Column(
            "deletion_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deletion_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_telegram_message_log_deletion_request_id",
        "telegram_message_log",
        ["deletion_request_id"],
        postgresql_where=sa.text("deletion_request_id IS NOT NULL"),
    )
    op.create_index(
        "ix_telegram_message_log_deleted",
        "telegram_message_log",
        ["tenant_id", "deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade():
    # M5: telegram_message_log Rollback
    op.drop_index("ix_telegram_message_log_deleted", "telegram_message_log")
    op.drop_index("idx_telegram_message_log_deletion_request_id", "telegram_message_log")
    op.drop_column("telegram_message_log", "deletion_request_id")
    op.drop_column("telegram_message_log", "deleted_at")

    op.drop_index("ix_llm_call_logs_deleted", "llm_call_logs")
    op.drop_column("llm_call_logs", "deleted_at")

    for table in reversed(_SOFT_DELETE_TABLES):
        op.drop_index(f"idx_{table}_deletion_request_id", table)
        op.drop_column(table, "deletion_request_id")
