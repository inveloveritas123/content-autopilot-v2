#!/usr/bin/env bash
# CI-Bootstrap: nach Alembic-Migrations einen Default-Tenant fuer E2E-Tests anlegen.
# Idempotent — Aufruf mehrfach safe.

set -euo pipefail

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-autopilot}"
DB_NAME="${DB_NAME:-content_autopilot_v2}"
DB_PASSWORD="${DB_PASSWORD:-citestpw}"
TENANT_KEY="${TENANT_KEY:-ci-test-tenant-key}"
TENANT_NAME="${TENANT_NAME:-CI Test Tenant}"

export PGPASSWORD="$DB_PASSWORD"

echo "[ci-bootstrap] Pruefe ob Tenant '$TENANT_KEY' existiert..."

EXISTING=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
  -tAc "SELECT 1 FROM tenants WHERE api_key='$TENANT_KEY' LIMIT 1" || echo "")

if [ "$EXISTING" = "1" ]; then
  echo "[ci-bootstrap] Tenant existiert bereits — kein Insert."
  exit 0
fi

echo "[ci-bootstrap] Lege Tenant an..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<SQL
INSERT INTO tenants (id, api_key, name, created_at, updated_at)
VALUES (gen_random_uuid(), '$TENANT_KEY', '$TENANT_NAME', NOW(), NOW())
ON CONFLICT (api_key) DO NOTHING;
SQL

echo "[ci-bootstrap] Done — Tenant '$TENANT_KEY' ist da."
