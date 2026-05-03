#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Content Autopilot v2 — Daily Backup Script
# Laedt pg_dump nach /opt/backup, optional GPG-verschluesselt.
# Log: /var/log/cap-v2-backup.log
#
# Cron-Job einrichten:
# echo "0 3 * * * root /opt/content-autopilot-v2/scripts/daily_backup.sh >> /var/log/cap-v2-backup.log 2>&1" > /etc/cron.d/cap-v2-backup
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

# ─── Logging (Datum-Prefix fuer Cron-Log) ───────────────────────
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
log()  { echo "$LOG_PREFIX $1"; }
log_ok()   { echo "$LOG_PREFIX [OK]   $1"; }
log_fail() { echo "$LOG_PREFIX [FAIL] $1" >&2; }
log_info() { echo "$LOG_PREFIX [INFO] $1"; }

# ─── Pfade ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="/opt/backup"
ENV_FILE="$REPO_DIR/.env"
LOG_FILE="/var/log/cap-v2-backup.log"

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
        log_fail "DB_PASSWORD nicht gesetzt und DATABASE_URL fehlt ebenfalls."
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

log "=== Daily Backup START — DB: $DB_NAME@$DB_HOST:$DB_PORT ==="

if ! command -v pg_dump &>/dev/null; then
    log_fail "pg_dump nicht gefunden! PostgreSQL-Client installiert?"
    exit 1
fi

# ─── Backup erstellen ────────────────────────────────────────────
DATE_STAMP=$(date +%Y%m%d)
BACKUP_BASE="$BACKUP_DIR/cap-v2-daily-${DATE_STAMP}"

if [ -n "${BACKUP_GPG_PASSPHRASE:-}" ]; then
    # GPG-verschluesselt
    BACKUP_FILE="${BACKUP_BASE}.sql.gz.gpg"
    log_info "GPG-Verschluesselung aktiv -> $BACKUP_FILE"

    if ! PGPASSWORD="$DB_PASS_PARSED" pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --no-password \
        | gzip \
        | gpg --batch --yes --symmetric \
              --cipher-algo AES256 \
              --passphrase-fd 3 \
              -o "$BACKUP_FILE" \
        3<<<"$BACKUP_GPG_PASSPHRASE"; then
        log_fail "Backup (GPG) fehlgeschlagen: $BACKUP_FILE"
        rm -f "$BACKUP_FILE"
        exit 1
    fi
else
    # Unkodiert (nur gzip)
    BACKUP_FILE="${BACKUP_BASE}.sql.gz"
    log_info "Kein GPG — einfaches gzip -> $BACKUP_FILE"

    if ! PGPASSWORD="$DB_PASS_PARSED" pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --no-password \
        | gzip > "$BACKUP_FILE"; then
        log_fail "Backup fehlgeschlagen: $BACKUP_FILE"
        rm -f "$BACKUP_FILE"
        exit 1
    fi
fi

BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
log_ok "Backup erstellt: $BACKUP_FILE ($BACKUP_SIZE)"

# ─── Rotation: Daily-Backups aelter als 30 Tage loeschen ─────────
DELETED_GZ=$(find "$BACKUP_DIR" -name "cap-v2-daily-*.sql.gz"     -mtime +30 -print -delete 2>/dev/null | wc -l)
DELETED_GPG=$(find "$BACKUP_DIR" -name "cap-v2-daily-*.sql.gz.gpg" -mtime +30 -print -delete 2>/dev/null | wc -l)
DELETED=$((DELETED_GZ + DELETED_GPG))
if [ "$DELETED" -gt 0 ]; then
    log_info "Rotation: $DELETED alte(r) Daily-Backup(s) geloescht (>30 Tage)"
else
    log_info "Rotation: keine alten Daily-Backups zum Loeschen"
fi

log "=== Daily Backup DONE ==="
