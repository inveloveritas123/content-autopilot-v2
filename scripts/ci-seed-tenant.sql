-- Seed-Script fuer CI-DB: legt Default-Tenant an mit api_key='ci-test-tenant-key'.
-- Wird beim Postgres-Container-Start via /docker-entrypoint-initdb.d/ ausgefuehrt
-- (laeuft NACH den anderen Init-Scripts, aber VOR Alembic-Migrations).
--
-- Tenant-Insert passiert nochmal nach Alembic via INSERT ... ON CONFLICT,
-- weil die tenants-Tabelle dann erst existiert.

-- pgvector ist ueber pgvector/pgvector:pg15-Image schon installiert,
-- braucht aber CREATE EXTENSION (Alembic-Migration 038 macht das auch).
CREATE EXTENSION IF NOT EXISTS vector;

-- Tenant wird in einem zweiten Schritt vom CI-Workflow nach Alembic
-- eingespielt (via curl /api/health/init oder direct SQL).
