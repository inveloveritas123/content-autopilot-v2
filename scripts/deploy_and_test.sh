#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Content Autopilot v2.0 — Deployment + QA Script
# Ausfuehren auf Server 152.53.142.163 als root
# Handhabt automatisch: v1→v2 Migration, alte Stacks, Port-Konflikte
# ═══════════════════════════════════════════════════════════════════
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

ERRORS=0
WARNINGS=0

# ─── STEP 0: Alten v1 Stack stoppen ─────────────────────────────
info "=== STEP 0: Alten v1 Stack stoppen (falls vorhanden) ==="

OLD_DIR="/opt/content-autopilot"
PROJECT_DIR="/opt/zukunftsbund-content-autopilot"
GITEA_URL="http://10.10.0.1:3000/meister/zukunftsbund-content-autopilot.git"

# Systemd-Services stoppen
for svc in content-autopilot content_autopilot streamlit-autopilot; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        info "Stoppe systemd service: $svc"
        systemctl stop "$svc" 2>/dev/null || true
        systemctl disable "$svc" 2>/dev/null || true
        ok "Service $svc gestoppt und deaktiviert"
    fi
done

# Alte Docker Container stoppen (falls im alten Verzeichnis)
if [ -d "$OLD_DIR" ] && [ -f "$OLD_DIR/docker-compose.yml" ]; then
    info "Stoppe alte Docker Container in $OLD_DIR..."
    cd "$OLD_DIR"
    docker compose down 2>/dev/null || docker-compose down 2>/dev/null || true
    ok "Alte Container gestoppt"
fi

# Prüfe ob Ports 8501/8502/8080 belegt sind
for port in 8501 8502 8080; do
    PID=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$PID" ]; then
        PROC=$(ps -p $PID -o comm= 2>/dev/null || echo "unbekannt")
        info "Port $port belegt von PID $PID ($PROC)"
        if [ "$PROC" = "nginx" ] || [ "$PROC" = "python3" ] || [ "$PROC" = "streamlit" ] || [ "$PROC" = "uvicorn" ]; then
            info "Stoppe Prozess auf Port $port (PID $PID)..."
            kill $PID 2>/dev/null || true
            sleep 1
            kill -9 $PID 2>/dev/null || true
            ok "Port $port freigegeben"
        else
            info "Port $port belegt von $PROC — bitte manuell pruefen"
            WARNINGS=$((WARNINGS + 1))
        fi
    else
        ok "Port $port ist frei"
    fi
done

# ─── STEP 1: Projektverzeichnis ──────────────────────────────────
info "=== STEP 1: Projekt-Setup ==="

if [ -d "$PROJECT_DIR/.git" ]; then
    info "Projekt existiert, ziehe Updates..."
    cd "$PROJECT_DIR"
    git fetch origin
    git reset --hard origin/main
    ok "Git pull erfolgreich"
else
    info "Klone Projekt..."
    git clone "$GITEA_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
    ok "Git clone erfolgreich"
fi

# ─── STEP 2: .env pruefen (mit v1-Migration) ────────────────────
info "=== STEP 2: .env Konfiguration ==="

# Falls keine .env im neuen Verzeichnis, aber eine im alten → kopieren + anpassen
if [ ! -f "$PROJECT_DIR/.env" ] && [ -f "$OLD_DIR/.env" ]; then
    info "Kopiere .env aus altem Verzeichnis $OLD_DIR/.env..."
    cp "$OLD_DIR/.env" "$PROJECT_DIR/.env"
    
    # Fix bekannte Typos aus v1: LITELM → LITELLM
    if grep -q "LITELM_BASE_URL" "$PROJECT_DIR/.env" 2>/dev/null; then
        info "Korrigiere LITELM → LITELLM Typos in .env..."
        sed -i 's/LITELM_BASE_URL/LITELLM_BASE_URL/g' "$PROJECT_DIR/.env"
        sed -i 's/LITELM_API_KEY/LITELLM_API_KEY/g' "$PROJECT_DIR/.env"
        ok "Typos in .env korrigiert"
    fi
    
    # Fehlende v2-Variablen ergaenzen
    if ! grep -q "DEFAULT_TENANT_KEY" "$PROJECT_DIR/.env" 2>/dev/null; then
        echo "" >> "$PROJECT_DIR/.env"
        echo "# v2: API-Schluessel fuer Mandanten-Authentifizierung" >> "$PROJECT_DIR/.env"
        echo "DEFAULT_TENANT_KEY=change_me_to_random_string" >> "$PROJECT_DIR/.env"
        info "DEFAULT_TENANT_KEY hinzugefuegt (bitte setzen!)"
    fi
    if ! grep -q "MCP_PORT" "$PROJECT_DIR/.env" 2>/dev/null; then
        echo "MCP_PORT=8080" >> "$PROJECT_DIR/.env"
    fi
    
    ok ".env aus v1 migriert"
fi

if [ ! -f "$PROJECT_DIR/.env" ]; then
    fail ".env Datei fehlt! Erstelle aus .env.example..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ACHTUNG: .env wurde aus .env.example erstellt.            ║"
    echo "║  Bitte API-Keys eintragen:                                 ║"
    echo "║    nano /opt/zukunftsbund-content-autopilot/.env           ║"
    echo "║                                                            ║"
    echo "║  Mindestens benoetigt:                                     ║"
    echo "║  - DB_PASSWORD                                             ║"
    echo "║  - GEMINI_API_KEY oder LITELLM_BASE_URL+LITELLM_API_KEY   ║"
    echo "║  - DEFAULT_TENANT_KEY                                      ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    ERRORS=$((ERRORS + 1))
fi

# .env validieren
source "$PROJECT_DIR/.env" 2>/dev/null || true

check_env() {
    local var_name=$1
    local required=$2
    local val="${!var_name}"
    if [ -z "$val" ] || [ "$val" = "change_me_to_something_secure" ] || [ "$val" = "your_gemini_api_key" ] || [ "$val" = "your_anthropic_api_key" ] || [ "$val" = "change_me_to_random_string" ] || [ "$val" = "your_requesty_api_key" ] || [ "$val" = "your_app_password" ]; then
        if [ "$required" = "required" ]; then
            fail "$var_name ist nicht gesetzt oder hat Platzhalter-Wert"
            ERRORS=$((ERRORS + 1))
        else
            info "$var_name ist nicht gesetzt (optional)"
            WARNINGS=$((WARNINGS + 1))
        fi
        return 1
    else
        ok "$var_name ist gesetzt"
        return 0
    fi
}

check_env "DB_PASSWORD" "required"
check_env "DEFAULT_TENANT_KEY" "required"

# LLM: mindestens Gemini ODER LiteLLM
HAS_LLM=0
if check_env "LITELLM_BASE_URL" "optional" 2>/dev/null; then
    check_env "LITELLM_API_KEY" "required"
    HAS_LLM=1
    ok "LLM via LiteLLM/Requesty Proxy"
fi
if check_env "GEMINI_API_KEY" "optional" 2>/dev/null; then
    HAS_LLM=1
    ok "LLM via direkten Gemini API Key"
fi
if [ $HAS_LLM -eq 0 ]; then
    fail "Kein LLM konfiguriert! Entweder GEMINI_API_KEY oder LITELLM_BASE_URL+LITELLM_API_KEY setzen."
    ERRORS=$((ERRORS + 1))
fi

check_env "NEXTCLOUD_URL" "optional"
check_env "NEXTCLOUD_USER" "optional"
check_env "NEXTCLOUD_PASSWORD" "optional"

# ─── STEP 3: PostgreSQL pruefen ──────────────────────────────────
info "=== STEP 3: PostgreSQL ==="

if command -v psql &>/dev/null; then
    if sudo -u postgres psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw content_autopilot; then
        ok "Datenbank 'content_autopilot' existiert (v1→v2 Alembic Migration wird automatisch ausgefuehrt)"
    else
        info "Erstelle Datenbank und User..."
        sudo -u postgres psql -c "CREATE USER autopilot WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null || true
        sudo -u postgres psql -c "CREATE DATABASE content_autopilot OWNER autopilot;" 2>/dev/null || true
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE content_autopilot TO autopilot;" 2>/dev/null || true
        ok "Datenbank erstellt"
    fi
    
    # Prüfe ob Alembic-Tabelle existiert (v1 hatte evtl. schon Migrationen)
    ALEMBIC_EXISTS=$(sudo -u postgres psql -d content_autopilot -tAc "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='alembic_version');" 2>/dev/null || echo "f")
    if [ "$ALEMBIC_EXISTS" = "t" ]; then
        CURRENT_REV=$(sudo -u postgres psql -d content_autopilot -tAc "SELECT version_num FROM alembic_version;" 2>/dev/null || echo "unbekannt")
        info "Aktuelle Alembic-Revision: $CURRENT_REV"
        info "v2 Migrationen (003_*) werden beim Backend-Start automatisch angewendet"
    else
        info "Keine Alembic-Tabelle gefunden — wird beim ersten Start erstellt"
    fi
else
    fail "psql nicht gefunden — PostgreSQL installiert?"
    ERRORS=$((ERRORS + 1))
fi

# ─── STEP 4: Docker Build ────────────────────────────────────────
info "=== STEP 4: Docker Build ==="

if [ $ERRORS -gt 0 ]; then
    fail "Es gibt $ERRORS Fehler. Bitte zuerst .env konfigurieren!"
    echo ""
    echo "Nach dem Konfigurieren erneut starten:"
    echo "  bash $PROJECT_DIR/scripts/deploy_and_test.sh"
    exit 1
fi

cd "$PROJECT_DIR"
info "Stoppe evtl. laufende v2-Container..."
docker compose down 2>/dev/null || true

info "Baue Container neu (kann 2-3 Minuten dauern)..."
docker compose build --no-cache
ok "Docker build erfolgreich"

info "Starte Container..."
docker compose up -d
ok "Container gestartet"

# Warte auf Backend
info "Warte auf Backend-Start (max 60s)..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:${APP_PORT:-8501}/api/health >/dev/null 2>&1; then
        ok "Backend antwortet"
        break
    fi
    if [ $i -eq 30 ]; then
        fail "Backend antwortet nicht nach 60s"
        echo "Logs:"
        docker compose logs backend --tail 30
        ERRORS=$((ERRORS + 1))
    fi
    sleep 2
done

# ─── STEP 5: QA Tests ────────────────────────────────────────────
info "=== STEP 5: QA Tests ==="

API_BASE="http://localhost:${APP_PORT:-8501}/api"
API_KEY="${DEFAULT_TENANT_KEY}"

# Test 1: Health Check
info "Test 1: Health Check"
HEALTH=$(curl -sf "$API_BASE/health" 2>/dev/null)
if echo "$HEALTH" | grep -q '"version": "2.0.0"'; then
    ok "Health Check — Version 2.0.0"
else
    fail "Health Check fehlgeschlagen: $HEALTH"
    ERRORS=$((ERRORS + 1))
fi

# Test 2: Dashboard
info "Test 2: Dashboard Endpoint"
DASH=$(curl -sf -H "X-API-Key: $API_KEY" "$API_BASE/dashboard" 2>/dev/null)
if [ $? -eq 0 ] && echo "$DASH" | python3 -m json.tool >/dev/null 2>&1; then
    ok "Dashboard Endpoint antwortet mit JSON"
else
    fail "Dashboard Endpoint fehlgeschlagen"
    ERRORS=$((ERRORS + 1))
fi

# Test 3: Sources Endpoint
info "Test 3: Sources Endpoint"
SOURCES=$(curl -sf -H "X-API-Key: $API_KEY" "$API_BASE/sources" 2>/dev/null)
if [ $? -eq 0 ]; then
    ok "Sources Endpoint erreichbar"
else
    fail "Sources Endpoint fehlgeschlagen"
    ERRORS=$((ERRORS + 1))
fi

# Test 4: Items Endpoint
info "Test 4: Items Endpoint"
ITEMS=$(curl -sf -H "X-API-Key: $API_KEY" "$API_BASE/items" 2>/dev/null)
if [ $? -eq 0 ]; then
    ok "Items Endpoint erreichbar"
else
    fail "Items Endpoint fehlgeschlagen"
    ERRORS=$((ERRORS + 1))
fi

# Test 5: Ideas Endpoint
info "Test 5: Ideas Endpoint"
IDEAS=$(curl -sf -H "X-API-Key: $API_KEY" "$API_BASE/ideas" 2>/dev/null)
if [ $? -eq 0 ]; then
    ok "Ideas Endpoint erreichbar"
else
    fail "Ideas Endpoint fehlgeschlagen"
    ERRORS=$((ERRORS + 1))
fi

# Test 6: Feedback Stats Endpoint
info "Test 6: Feedback Stats Endpoint"
FSTATS=$(curl -sf -H "X-API-Key: $API_KEY" "$API_BASE/feedback/stats" 2>/dev/null)
if [ $? -eq 0 ]; then
    ok "Feedback Stats Endpoint erreichbar"
else
    fail "Feedback Stats Endpoint fehlgeschlagen"
    ERRORS=$((ERRORS + 1))
fi

# Test 7: Celery Worker
info "Test 7: Celery Worker Status"
if docker compose ps | grep -q "celery-worker.*Up"; then
    ok "Celery Worker laeuft"
else
    fail "Celery Worker laeuft nicht"
    docker compose logs celery-worker --tail 10
    ERRORS=$((ERRORS + 1))
fi

# Test 8: Celery Beat
info "Test 8: Celery Beat Status"
if docker compose ps | grep -q "celery-beat.*Up"; then
    ok "Celery Beat laeuft"
else
    fail "Celery Beat laeuft nicht"
    docker compose logs celery-beat --tail 10
    ERRORS=$((ERRORS + 1))
fi

# Test 9: MCP Server
info "Test 9: MCP Server"
if docker compose ps | grep -q "mcp-server.*Up"; then
    ok "MCP Server Container laeuft"
    MCP_PORT_VAL=${MCP_PORT:-8080}
    if curl -sf "http://localhost:$MCP_PORT_VAL/" >/dev/null 2>&1 || curl -sf "http://localhost:$MCP_PORT_VAL/sse" -o /dev/null -w "%{http_code}" 2>&1 | grep -qE "200|405|404"; then
        ok "MCP Server Port $MCP_PORT_VAL erreichbar"
    else
        info "MCP Server Port $MCP_PORT_VAL nicht per HTTP erreichbar (SSE-Transport, kann normal sein)"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    fail "MCP Server laeuft nicht"
    docker compose logs mcp-server --tail 10
    ERRORS=$((ERRORS + 1))
fi

# Test 10: Alembic Migration Check
info "Test 10: Datenbank-Migrationen"
MIGRATION_LOG=$(docker compose logs backend 2>/dev/null | grep -i "migration" | tail -5)
if echo "$MIGRATION_LOG" | grep -qi "running database migrations"; then
    ok "Alembic Migrationen wurden ausgefuehrt (auto-run on startup)"
else
    info "Migration-Log nicht gefunden, pruefe manuell..."
    docker compose exec -T backend alembic current 2>/dev/null && ok "Alembic erreichbar" || fail "Alembic check fehlgeschlagen"
fi

# Test 11: Alembic auf neuester Revision
info "Test 11: Alembic Revision Check"
ALEMBIC_HEAD=$(docker compose exec -T backend alembic heads 2>/dev/null | head -1 || echo "")
ALEMBIC_CURRENT=$(docker compose exec -T backend alembic current 2>/dev/null | head -1 || echo "")
if [ -n "$ALEMBIC_HEAD" ] && [ -n "$ALEMBIC_CURRENT" ]; then
    if echo "$ALEMBIC_CURRENT" | grep -q "head"; then
        ok "Datenbank ist auf neuester Migration (head)"
    else
        info "Alembic current: $ALEMBIC_CURRENT / head: $ALEMBIC_HEAD"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    info "Konnte Alembic-Revision nicht pruefen"
    WARNINGS=$((WARNINGS + 1))
fi

# ─── STEP 6: Zusammenfassung ─────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  DEPLOYMENT + QA ZUSAMMENFASSUNG"
echo "═══════════════════════════════════════════════════════════════"
echo ""

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}  ALLES OK — $WARNINGS Warnungen${NC}"
    echo ""
    echo "  Endpoints:"
    echo "    Frontend:  http://152.53.142.163:${APP_PORT:-8501}"
    echo "    API:       http://152.53.142.163:${APP_PORT:-8501}/api"
    echo "    API Docs:  http://152.53.142.163:${APP_PORT:-8501}/docs"
    echo "    MCP:       http://152.53.142.163:${MCP_PORT:-8080}"
    echo ""
    echo "  Docker Status:"
    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
else
    echo -e "${RED}  $ERRORS FEHLER, $WARNINGS Warnungen${NC}"
    echo ""
    echo "  Bitte Fehler beheben und erneut starten:"
    echo "    bash $PROJECT_DIR/scripts/deploy_and_test.sh"
fi
echo ""
echo "═══════════════════════════════════════════════════════════════"
