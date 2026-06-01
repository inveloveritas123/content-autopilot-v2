#!/bin/bash
# ====
# content-autopilot-v2 — Bootstrap Setup Script
#
# Zweck:   Idempotentes Setup auf frischem Debian/Ubuntu-Server.
#          Installiert Docker, validiert .env, pullt/baut Images, startet Stack,
#          wartet auf Health und fuehrt Smoke-Test durch.
#
# Nutzung: bash setup.sh [--non-interactive] [--rebuild] [--help]
#
# Flags:
#   --non-interactive  Kein interaktiver Prompt; .env muss bereits konfiguriert
#                      sein. Geeignet fuer CI/CD.
#   --rebuild          Immer `docker compose build` statt `docker compose pull`.
#   --help             Diese Hilfe ausgeben und beenden.
#
# Voraussetzungen:
#   - Debian oder Ubuntu
#   - root oder sudo-Rechte
#   - PostgreSQL laeuft auf dem Host (Port 5432), DB/User bereits angelegt
#   - .env befuellt (oder: .env.example vorhanden, damit setup.sh eine Kopie
#     erstellen und pruefen kann)
#
# Compose-File:        docker-compose.v2.yml
# App-Port (nginx):    ${APP_PORT:-8601}
# Health-URL:          http://localhost:8601/api/health
# ====
set -euo pipefail

# ─── Farben (nur wenn echtes TTY) ─────────────────────────────────────────────
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' CYAN='' BOLD='' NC=''
fi

# ─── Logging-Helfer ───────────────────────────────────────────────────────────
ts()   { date '+%H:%M:%S'; }
ok()   { echo -e "$(ts) ${GREEN}[OK]${NC}    $1"; }
fail() { echo -e "$(ts) ${RED}[FAIL]${NC}  $1" >&2; }
info() { echo -e "$(ts) ${CYAN}[INFO]${NC}  $1"; }
warn() { echo -e "$(ts) ${YELLOW}[WARN]${NC}  $1"; }
step() { echo -e "\n$(ts) ${BOLD}${CYAN}=== $1 ===${NC}"; }
die()  {
    fail "$1"
    if [ -n "${2:-}" ]; then
        echo -e "  ${YELLOW}Hinweis:${NC} $2" >&2
    fi
    exit 1
}

# ─── Konstanten ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.v2.yml"
ENV_FILE="${SCRIPT_DIR}/.env"
ENV_EXAMPLE="${SCRIPT_DIR}/.env.example"

HEALTH_RETRIES=30          # 30 × 5s = 150s (2.5 min)
HEALTH_INTERVAL=5
# HEALTH_URL wird nach dem .env-Source gesetzt (STEP 2)

# ─── Flag-Parsing ─────────────────────────────────────────────────────────────
NON_INTERACTIVE=false
REBUILD=false

for arg in "$@"; do
    case "$arg" in
        --non-interactive) NON_INTERACTIVE=true ;;
        --rebuild)         REBUILD=true ;;
        --help|-h)
            sed -n '/^# ====/,/^# ====/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            die "Unbekannter Parameter: $arg" \
                "Erlaubte Flags: --non-interactive, --rebuild, --help"
            ;;
    esac
done

# ─── Compose-File pruefen ─────────────────────────────────────────────────────
[ -f "$COMPOSE_FILE" ] || die \
    "docker-compose.v2.yml nicht gefunden: $COMPOSE_FILE" \
    "Script muss aus dem Repo-Root laufen oder im Repo-Root liegen."

# ─── STEP 1: Prerequisites ────────────────────────────────────────────────────
step "STEP 1: Prerequisites pruefen"

install_via_apt() {
    local pkg="$1"
    info "$pkg fehlt — installiere via apt-get..."
    if ! command -v apt-get &>/dev/null; then
        die "apt-get nicht gefunden. Nur Debian/Ubuntu wird unterstuetzt." \
            "Installiere $pkg manuell und starte setup.sh erneut."
    fi
    apt-get update -qq
    apt-get install -y -qq "$pkg" || die "Installation von $pkg fehlgeschlagen."
    ok "$pkg installiert"
}

# gzip
if command -v gzip &>/dev/null; then
    ok "gzip vorhanden ($(gzip --version 2>&1 | head -1))"
else
    install_via_apt gzip
fi

# curl
if command -v curl &>/dev/null; then
    ok "curl vorhanden"
else
    install_via_apt curl
fi

# Docker (Engine + Compose Plugin)
if command -v docker &>/dev/null; then
    DOCKER_VER=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unbekannt")
    ok "Docker vorhanden (v${DOCKER_VER})"
else
    info "Docker nicht gefunden — installiere via get.docker.com..."
    curl -fsSL https://get.docker.com | sh || \
        die "Docker-Installation fehlgeschlagen." \
            "Installiere Docker manuell: https://docs.docker.com/engine/install/"
    ok "Docker installiert"
fi

# Docker Compose Plugin (v2: `docker compose`)
if docker compose version &>/dev/null 2>&1; then
    DC_VER=$(docker compose version --short 2>/dev/null || echo "unbekannt")
    ok "Docker Compose Plugin vorhanden (v${DC_VER})"
else
    info "Docker Compose Plugin fehlt — installiere docker-compose-plugin..."
    if command -v apt-get &>/dev/null; then
        apt-get update -qq
        apt-get install -y -qq docker-compose-plugin || \
            die "docker-compose-plugin Installation fehlgeschlagen." \
                "Installiere Docker Compose Plugin manuell: https://docs.docker.com/compose/install/"
        ok "docker-compose-plugin installiert"
    else
        die "Docker Compose Plugin fehlt und apt-get nicht verfuegbar." \
            "Installiere das Compose Plugin manuell und starte setup.sh erneut."
    fi
fi

# ─── STEP 2: .env validieren ─────────────────────────────────────────────────
step "STEP 2: .env validieren"

if [ ! -f "$ENV_FILE" ]; then
    if [ "$NON_INTERACTIVE" = true ]; then
        die ".env fehlt und --non-interactive ist gesetzt." \
            "Erstelle .env aus .env.example und setze DB_PASSWORD sowie DEFAULT_TENANT_KEY:
  cp ${ENV_EXAMPLE} ${ENV_FILE}
  nano ${ENV_FILE}"
    fi

    # Interaktiver Modus: aus .env.example kopieren
    if [ ! -f "$ENV_EXAMPLE" ]; then
        die ".env.example nicht gefunden: ${ENV_EXAMPLE}" \
            "Stelle sicher, dass .env.example im Repo-Root liegt."
    fi

    info ".env fehlt — kopiere aus .env.example..."
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    warn ".env aus .env.example erstellt. Pflichtfelder muessen gesetzt sein:"
    warn "  DB_PASSWORD        — PostgreSQL-Passwort fuer User 'autopilot'"
    warn "  DEFAULT_TENANT_KEY — API-Key fuer den Default-Tenant (kein 'changeme')"
    warn "Datei: ${ENV_FILE}"
fi

# .env einlesen (ohne set -a, um keine versehentlichen Exporte)
# shellcheck source=/dev/null
set -o allexport
source "$ENV_FILE"
set +o allexport

# Pflichtfeld-Pruefung
ENV_ERRORS=0

check_required() {
    local var="$1"
    local val="${!var:-}"
    if [ -z "$val" ]; then
        fail "Pflichtfeld ${var} ist nicht gesetzt in ${ENV_FILE}"
        ENV_ERRORS=$((ENV_ERRORS + 1))
        return
    fi
    # Platzhalter-Erkennung
    case "$val" in
        changeme*|change_me*|CHANGEME*|your_*|example*|placeholder*)
            fail "Pflichtfeld ${var} hat noch einen Platzhalter-Wert: '${val}'"
            ENV_ERRORS=$((ENV_ERRORS + 1))
            return
            ;;
    esac
    ok "${var} ist gesetzt"
}

check_required "DB_PASSWORD"
check_required "DEFAULT_TENANT_KEY"

if [ "$ENV_ERRORS" -gt 0 ]; then
    die "${ENV_ERRORS} Pflichtfeld(er) fehlen oder enthalten Platzhalter." \
        "Bearbeite ${ENV_FILE} und starte setup.sh erneut."
fi

# APP_PORT aus .env lesen (Fallback 8601)
APP_PORT="${APP_PORT:-8601}"
HEALTH_URL="http://localhost:${APP_PORT}/api/health"
info "App-Port: ${APP_PORT} | Health-URL: ${HEALTH_URL}"

# ─── STEP 3: Images pullen oder bauen ─────────────────────────────────────────
step "STEP 3: Images pullen / bauen"

cd "$SCRIPT_DIR"

if [ "$REBUILD" = true ]; then
    info "--rebuild gesetzt — baue Images lokal..."
    docker compose -f "$COMPOSE_FILE" build \
        || die "docker compose build fehlgeschlagen." \
               "Details: docker compose -f ${COMPOSE_FILE} logs"
    ok "Images gebaut"
elif [ -n "${IMAGE_PREFIX:-}" ]; then
    # Registry konfiguriert (Gitea / GHCR / eigene) → pullen, mit Build-Fallback
    info "IMAGE_PREFIX gesetzt (${IMAGE_PREFIX}) — versuche Pull aus Registry..."
    if docker compose -f "$COMPOSE_FILE" pull 2>&1; then
        ok "Images gepullt"
    else
        warn "Pull fehlgeschlagen (Registry nicht erreichbar?) — baue lokal..."
        docker compose -f "$COMPOSE_FILE" build \
            || die "docker compose build fehlgeschlagen." \
                   "Details: docker compose -f ${COMPOSE_FILE} build (Fehler oben)"
        ok "Images lokal gebaut"
    fi
else
    # Standard (GitHub-Deploy): lokal bauen — keine Registry / kein Gitea noetig
    info "Kein IMAGE_PREFIX gesetzt — baue Images lokal (Standard, ohne Registry)..."
    docker compose -f "$COMPOSE_FILE" build \
        || die "docker compose build fehlgeschlagen." \
               "Details: docker compose -f ${COMPOSE_FILE} build (Fehler oben)"
    ok "Images lokal gebaut"
fi

# ─── STEP 4: Stack hochfahren ─────────────────────────────────────────────────
step "STEP 4: Stack hochfahren"

# Idempotenz: pruefen ob bereits laeuft
RUNNING_CONTAINERS=$(docker compose -f "$COMPOSE_FILE" ps --status running -q 2>/dev/null | wc -l)

if [ "$RUNNING_CONTAINERS" -gt 0 ]; then
    info "Stack laeuft bereits (${RUNNING_CONTAINERS} Container aktiv) — kein Neustart."
    info "Um den Stack neu zu starten: docker compose -f ${COMPOSE_FILE} restart"
else
    docker compose -f "$COMPOSE_FILE" up -d \
        || die "docker compose up -d fehlgeschlagen." \
               "Logs pruefen: docker compose -f ${COMPOSE_FILE} logs"
    ok "Stack gestartet"
fi

# ─── STEP 5: Warten bis Backend healthy ───────────────────────────────────────
step "STEP 5: Warte auf Backend (max $((HEALTH_RETRIES * HEALTH_INTERVAL))s)"

ATTEMPT=0
HEALTHY=false
while [ "$ATTEMPT" -lt "$HEALTH_RETRIES" ]; do
    ATTEMPT=$((ATTEMPT + 1))
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${HEALTH_URL}" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        HEALTHY=true
        ok "Backend antwortet (HTTP ${HTTP_CODE}) nach ${ATTEMPT} Versuchen"
        break
    fi
    info "Versuch ${ATTEMPT}/${HEALTH_RETRIES} — HTTP ${HTTP_CODE} — warte ${HEALTH_INTERVAL}s..."
    sleep "$HEALTH_INTERVAL"
done

if [ "$HEALTHY" = false ]; then
    fail "Backend antwortet nicht nach $((HEALTH_RETRIES * HEALTH_INTERVAL))s"
    echo ""
    echo -e "  ${YELLOW}Logs der relevanten Services:${NC}"
    docker compose -f "$COMPOSE_FILE" logs --tail 30 backend-v2 2>/dev/null || true
    docker compose -f "$COMPOSE_FILE" logs --tail 10 nginx-v2 2>/dev/null || true
    die "Health-Check gescheitert." \
        "Vollstaendige Logs: docker compose -f ${COMPOSE_FILE} logs"
fi

# ─── STEP 6: Smoke-Test ───────────────────────────────────────────────────────
step "STEP 6: Smoke-Test"

SMOKE_BODY=$(curl -s "${HEALTH_URL}" 2>/dev/null || echo "")
SMOKE_HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${HEALTH_URL}" 2>/dev/null || echo "000")

# HTTP 5xx ist ein Fehler, 200 mit ok/degraded ist akzeptabel
if [[ "$SMOKE_HTTP" =~ ^5 ]]; then
    fail "Smoke-Test: HTTP ${SMOKE_HTTP} (Server-Fehler)"
    echo "  Response: ${SMOKE_BODY}"
    die "Smoke-Test fehlgeschlagen." \
        "Backend-Logs pruefen: docker compose -f ${COMPOSE_FILE} logs backend-v2"
fi

# Body-Check: {"status":"ok"} oder {"status":"degraded"} akzeptiert
if echo "$SMOKE_BODY" | grep -qE '"status"\s*:\s*"(ok|degraded)"'; then
    STATUS_VAL=$(echo "$SMOKE_BODY" | grep -oE '"status"\s*:\s*"[^"]+"' | head -1)
    ok "Smoke-Test bestanden — ${STATUS_VAL} (HTTP ${SMOKE_HTTP})"
else
    warn "Smoke-Test: unerwarteter Response-Body (HTTP ${SMOKE_HTTP})"
    warn "Body: ${SMOKE_BODY}"
    warn "Erwartet: {\"status\":\"ok\"} oder {\"status\":\"degraded\"}"
    # Kein harter Fehler — HTTP war nicht 5xx, Stack laeuft
fi

# ─── Abschluss-Summary ────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  content-autopilot-v2 — Setup erfolgreich abgeschlossen${NC}"
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${CYAN}Frontend / API:${NC}  http://<server-ip>:${APP_PORT}"
echo -e "  ${CYAN}API Docs:${NC}        http://<server-ip>:${APP_PORT}/docs"
echo -e "  ${CYAN}Health:${NC}          ${HEALTH_URL}"
MCP_PORT_VAL="${MCP_PORT:-8180}"
echo -e "  ${CYAN}MCP Server:${NC}      http://<server-ip>:${MCP_PORT_VAL}"
echo ""
echo -e "  ${CYAN}Container-Status:${NC}"
docker compose -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || \
    docker compose -f "$COMPOSE_FILE" ps 2>/dev/null || true
echo ""
echo -e "  ${YELLOW}Logs:${NC}  docker compose -f ${COMPOSE_FILE} logs -f"
echo ""
