"""Row-Level-Security (RLS) Multi-Tenant-Isolation.

Revision ID: 058
Revises: 057
Create Date: 2026-07-21

Kontext: KEIN Prod, keine Altdaten (nur Testkunden bereitstehend) — greenfield,
daher keine komplexe Datenmigration nötig. Trotzdem sauberes
Expand-Migrate-Contract-Muster:

TEIL A — tenant_id-Typ-Konsolidierung (Expand+Migrate in einem Schritt, da
greenfield/leere Testtabellen): 14 "DIRTY"-Tabellen hatten tenant_id bisher als
Text/String OHNE FK auf tenants.id. Wir casten auf UUID und ergänzen die FK.
Der `USING tenant_id::uuid`-Cast ist sicher, weil es keine Prod-Altdaten gibt —
nur Testkunden-Rows, die bereits valide UUID-Strings enthalten (oder die Tabelle
ist leer).

Besonderheiten (siehe Verifikation gegen die create_table-Migrationen):
- tenant_telegram_link: zusammengesetzter PK (tenant_id, telegram_user_id, channel)
  seit Migration 040 (ursprünglich (tenant_id, telegram_user_id) in 019). Ein
  ALTER COLUMN ... TYPE auf eine PK-Spalte ist in Postgres erlaubt, solange keine
  FK anderer Tabellen auf diesen PK zeigt (hier nicht der Fall) — der PK/Index
  wird automatisch mitgeschrieben, kein DROP/CREATE nötig.
- daily_cost_tenant: zusammengesetzter PK (tenant_id, date) seit Migration 018 —
  selbes Prinzip, kein Index-Drop nötig.
- backtest_runs (023) und tenant_review_queue (025): PK ist die eigene `id`-Spalte
  (String(36)), tenant_id ist NICHT Teil des PK, nur ein normaler Text-Feld
  (tenant_review_queue hat zusätzlich einen Composite-Index
  ix_review_queue_tenant_status auf (tenant_id, status) aus 025 — bleibt beim
  TYPE-Change automatisch konsistent, kein Rebuild nötig).
- tenant_bot_config (031): PK ist `id` (Text), tenant_id trägt eine
  UniqueConstraint (kein Index-Drop nötig für TYPE-Change).
- Alle anderen 10 Tabellen (tenant_customer_context, tenant_voice_profile,
  tenant_audience_avatar, wizard_session, voice_drift_observation,
  setup_pipeline_run, telegram_message_log, bot_session, tenant_customer_values)
  haben tenant_id nur als normale (indizierte) Spalte, kein PK-Bestandteil.

TEIL B — RLS-Policies auf allen 41 Tenant-Tabellen (den 14 obigen + 27 bereits
UUID-typisierten Tabellen). `FORCE ROW LEVEL SECURITY` ist bewusst gesetzt, weil
die App-DB-Rolle oft Tabellen-Owner ist und RLS für den Owner sonst NICHT
erzwungen würde (Postgres-Default). Der GUC `app.tenant_id` wird von
`services/rls.py::set_rls_tenant` per `SET LOCAL` gesetzt.

Fail-closed-Kontrakt (siehe services/rls.py): Ist kein Tenant gesetzt, schreibt
die App den Leerstring '' in `app.tenant_id` (NICHT NULL) — `''::uuid` würde
einen Cast-Fehler werfen und crashen statt fail-closed zu greifen. Deshalb
`NULLIF(current_setting('app.tenant_id', true), '')::uuid`: der Leerstring wird
zu SQL-NULL normalisiert, `tenant_id = NULL` matcht in SQL nie eine Zeile ->
fail-closed ohne Crash. Der zweite Parameter `true` von current_setting ist
missing_ok (kein Fehler, wenn die GUC nie gesetzt wurde).
"""

import sqlalchemy as sa

from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# TEIL A — Tabellen mit tenant_id als Text/String OHNE FK (Typ-Konsolidierung).
# ---------------------------------------------------------------------------
_DIRTY_TABLES = (
    "tenant_customer_context",
    "tenant_voice_profile",
    "tenant_audience_avatar",
    "wizard_session",
    "voice_drift_observation",
    "daily_cost_tenant",
    "setup_pipeline_run",
    "tenant_telegram_link",
    "telegram_message_log",
    "bot_session",
    "backtest_runs",
    "tenant_review_queue",
    "tenant_bot_config",
    "tenant_customer_values",
)

# ---------------------------------------------------------------------------
# TEIL B — alle 41 Tenant-Tabellen (14 DIRTY oben + 27 bereits UUID) bekommen
# RLS-Policies. Reihenfolge: DIRTY zuerst (dann sind sie auch UUID), danach
# die restlichen 27, die tenant_id bereits als UUID+FK führen.
# ---------------------------------------------------------------------------
_CLEAN_TABLES = (
    "campaigns",
    "carousel_templates",
    "company_profile",
    "content_dna_profiles",
    "content_ideas",
    "content_performances",
    "content_pieces",
    "deletion_requests",
    "dialogue_questions",
    "entrepreneur_answers",
    "hook_library",
    "idea_selection_logs",
    "idea_variants",
    "llm_call_logs",
    "llm_providers",
    "memory_chunks",
    "profile_field_provenance",
    "projects",
    "quality_metrics",
    "research_findings",
    "scheduled_posts",
    "source_items",
    "sources",
    "tenant_branding",
    "tenant_reservoir",
    "throttle_events",
    "voice_feedback",
)

_RLS_TABLES = _DIRTY_TABLES + _CLEAN_TABLES

# Zugriff auf eine Zeile ist erlaubt, wenn ihr tenant_id dem Session-Tenant
# entspricht ODER der explizite Cross-Tenant-Bypass gesetzt ist (nightly Purge,
# Admin-Cross-Tenant — via services.rls.set_rls_bypass, auditierbar).
_RLS_CONDITION = (
    "("
    "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    " OR current_setting('app.rls_bypass', true) = 'on'"
    ")"
)


def upgrade() -> None:
    # --- TEIL A: tenant_id Text -> UUID + FK auf tenants.id ---
    for table in _DIRTY_TABLES:
        op.execute(
            sa.text(f"ALTER TABLE {table} ALTER COLUMN tenant_id TYPE uuid USING tenant_id::uuid")
        )
        op.execute(
            sa.text(
                f"ALTER TABLE {table} ADD CONSTRAINT fk_{table}_tenant "
                f"FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE"
            )
        )

    # --- TEIL B: RLS-Policies auf allen 41 Tenant-Tabellen ---
    for table in _RLS_TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY tenant_isolation ON {table} "
                f"USING ({_RLS_CONDITION}) "
                f"WITH CHECK ({_RLS_CONDITION})"
            )
        )


def downgrade() -> None:
    # --- TEIL B rückgängig: Policies droppen, RLS disablen ---
    for table in reversed(_RLS_TABLES):
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    # --- TEIL A rückgängig: FK droppen, tenant_id zurück auf text ---
    # Best effort (greenfield, unkritisch): Es gibt keine Prod-Altdaten, die
    # einen exakten Roundtrip erfordern würden.
    for table in reversed(_DIRTY_TABLES):
        op.execute(sa.text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_tenant"))
        op.execute(
            sa.text(f"ALTER TABLE {table} ALTER COLUMN tenant_id TYPE text USING tenant_id::text")
        )
