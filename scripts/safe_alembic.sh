#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Content Autopilot v2 — Safe Alembic Wrapper
# Erstellt Pre-Migration-Snapshot, fuehrt Alembic aus, verifiziert.
#
# Aufruf:
#   scripts/safe_alembic.sh "upgrade head"
#   scripts/safe_alembic.sh "downgrade -1"
#   scripts/safe_alembic.sh --no-snapshot "upgrade head"
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1" >&2; }
info() { echo -e "${YELLOW}[INFO]${NC} $1"; }
step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# ─── Argumente parsen ────────────────────────────────────────────
SKIP_SNAPSHOT=0
ALEMBIC_ARGS=()

for arg in "$@"; do
    if [ "$arg" = "--no-snapshot" ]; then
        SKIP_SNAPSHOT=1
    else
        ALEMBIC_ARGS+=("$arg")
    fi
done

if [ ${#ALEMBIC_ARGS[@]} -eq 0 ]; then
    fail "Kein Alembic-Befehl angegeben."
    echo "Aufruf: $0 [--no-snapshot] \"upgrade head\""
    echo "        $0 [--no-snapshot] \"downgrade -1\""
    exit 1
fi

ALEMBIC_CMD="${ALEMBIC_ARGS[*]}"  # nur fuer Logging

# ─── Pfade ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="/opt/backup"
COMPOSE_FILE="$REPO_DIR/docker-compose.v2.yml"
ENV_FILE="$REPO_DIR/.env"

# ─── .env laden ──────────────────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
    # shellcheck source=/dev/null
    set -a
    source "$ENV_FILE"
    set +a
fi

# ─── DATABASE_URL aus .env oder Fallback ─────────────────────────
if [ -z "${DATABASE_URL:-}" ]; then
    DB_PASS="${DB_PASSWORD:-}"
    if [ -z "$DB_PASS" ]; then
        fail "DB_PASSWORD nicht gesetzt und DATABASE_URL fehlt ebenfalls."
        exit 1
    fi
    DATABASE_URL="postgresql://autopilot:${DB_PASS}@localhost:5432/content_autopilot_v2"
fi

# DATABASE_URL parsen: postgresql://user:pass@host:port/dbname
_url_stripped="${DATABASE_URL#postgresql://}"
_url_stripped="${_url_stripped#postgres://}"
DB_USER="${_url_stripped%%:*}"
_after_user="${_url_stripped#*:}"
DB_PASS_PARSED="${_after_user%%@*}"
_after_pass="${_after_user#*@}"
DB_HOST="${_after_pass%%:*}"
_after_host="${_after_pass#*:}"
DB_PORT="${_after_host%%/*}"
DB_NAME="${_after_host#*/}"

# ─── Backup-Verzeichnis sicherstellen ────────────────────────────
mkdir -p "$BACKUP_DIR"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  SAFE ALEMBIC — Content Autopilot v2"
echo "  Befehl: alembic $ALEMBIC_CMD"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ─── STEP 1: Pre-Migration-Snapshot ──────────────────────────────
if [ "$SKIP_SNAPSHOT" -eq 1 ]; then
    info "STEP 1: Snapshot uebersprungen (--no-snapshot)"
else
    step "STEP 1: Pre-Migration-Snapshot erstellen..."

    SNAPSHOT_FILE="$BACKUP_DIR/cap-v2-pre-migration-$(date +%Y%m%d-%H%M%S).sql.gz"

    if ! command -v pg_dump &>/dev/null; then
        fail "pg_dump nicht gefunden! PostgreSQL-Client installiert?"
        exit 1
    fi

    info "Dump: $SNAPSHOT_FILE"
    info "DB:   $DB_NAME@$DB_HOST:$DB_PORT (User: $DB_USER)"

    # pg_dump mit PGPASSWORD, kein .pgpass noetig
    if ! PGPASSWORD="$DB_PASS_PARSED" pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --no-password \
        | gzip > "$SNAPSHOT_FILE"; then
        fail "pg_dump fehlgeschlagen! Migration wird ABGEBROCHEN."
        rm -f "$SNAPSHOT_FILE"
        exit 1
    fi

    SNAPSHOT_SIZE=$(du -sh "$SNAPSHOT_FILE" | cut -f1)
    ok "Snapshot erstellt: $SNAPSHOT_FILE ($SNAPSHOT_SIZE)"
fi

# ─── STEP 2: Alembic Migration ausfuehren ────────────────────────
step "STEP 2: Alembic '$ALEMBIC_CMD' ausfuehren..."

if [ ! -f "$COMPOSE_FILE" ]; then
    fail "docker-compose.v2.yml nicht gefunden: $COMPOSE_FILE"
    exit 1
fi

if ! docker compose -f "$COMPOSE_FILE" exec -T backend-v2 alembic "${ALEMBIC_ARGS[@]}"; then
    fail "Alembic '$ALEMBIC_CMD' fehlgeschlagen!"
    if [ "$SKIP_SNAPSHOT" -eq 0 ]; then
        echo ""
        echo -e "${RED}  Snapshot zum Rollback:${NC}"
        echo "    $SNAPSHOT_FILE"
        echo "  Restore-Anleitung: docs/RESTORE.md"
    fi
    exit 1
fi

ok "Alembic '$ALEMBIC_CMD' erfolgreich"

# ─── STEP 3: Verify ──────────────────────────────────────────────
step "STEP 3: Alembic current pruefen..."

CURRENT_REV=$(docker compose -f "$COMPOSE_FILE" exec -T backend-v2 alembic current 2>/dev/null | head -1 || echo "unbekannt")
ok "Aktuelle Revision: $CURRENT_REV"

# ─── STEP 4: Alte Snapshots rotieren (>30 Tage) ──────────────────
step "STEP 4: Snapshot-Rotation (>30 Tage)..."

DELETED=$(find "$BACKUP_DIR" -name "cap-v2-pre-migration-*.sql.gz" -mtime +30 -print -delete 2>/dev/null | wc -l)
if [ "$DELETED" -gt 0 ]; then
    info "$DELETED alte(r) Snapshot(s) geloescht"
else
    ok "Keine alten Snapshots zum Loeschen"
fi

# ─── Zusammenfassung ─────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "${GREEN}  MIGRATION ERFOLGREICH${NC}"
if [ "$SKIP_SNAPSHOT" -eq 0 ]; then
    echo "  Snapshot: $SNAPSHOT_FILE ($SNAPSHOT_SIZE)"
fi
echo "  Revision: $CURRENT_REV"
echo "═══════════════════════════════════════════════════════════════"
echo ""
