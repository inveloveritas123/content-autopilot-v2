#!/bin/bash
# ============================================================
# Content Autopilot v2 — Issue Agent Runner
# Wird vom Director-Webhook aufgerufen wenn ein neues Issue
# im Gitea Repo meister/content-autopilot-v2 erstellt wird.
#
# Aufruf: ./issue_agent.sh <issue_nr> "<title>" "<body>"
# ============================================================

set -euo pipefail

ISSUE_NR="${1:-}"
ISSUE_TITLE="${2:-}"
ISSUE_BODY="${3:-}"
LOG_DIR="/opt/content-autopilot-v2/scripts/agent_logs"
GITEA_TOKEN="${GITEA_TOKEN:?set GITEA_TOKEN env var}"  # Secret entfernt bei GitHub-Migration; aus Umgebung lesen
GITEA_API="http://localhost:3000/api/v1/repos/meister/content-autopilot-v2"
TELEGRAM_SCRIPT="/opt/content-autopilot-v2/scripts/notify_robert.py"

mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/issue_${ISSUE_NR}_$(date +%Y%m%d_%H%M%S).log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOGFILE"; }

if [ -z "$ISSUE_NR" ]; then
    echo "Usage: $0 <issue_nr> <title> <body>"
    exit 1
fi

log "=== Issue Agent gestartet fuer #${ISSUE_NR}: ${ISSUE_TITLE} ==="

# Labels des Issues lesen
LABELS=$(curl -sf "${GITEA_API}/issues/${ISSUE_NR}/labels?token=${GITEA_TOKEN}" \
    | python3 -c "import sys,json; labels=json.load(sys.stdin); print(','.join(l['name'] for l in labels))" 2>/dev/null || echo "")

log "Labels: ${LABELS}"

# Freigabe-Check: Braucht Robert Genehmigung?
NEEDS_APPROVAL=false
for LABEL in freigabe-robert sicherheit kritisch security; do
    if echo "$LABELS" | grep -qi "$LABEL"; then
        NEEDS_APPROVAL=true
        break
    fi
done

# Zusaetzlich: Titel/Body auf Sicherheitsthemen pruefen
if echo "${ISSUE_TITLE}${ISSUE_BODY}" | grep -qiE "(auth|firewall|iptables|ufw|ssl|tls|passwor|secret|api.key|privat|sicherheit|security|permission|root|sudo|cron|systemd|postgresql.conf|pg_hba)"; then
    NEEDS_APPROVAL=true
    log "Sicherheitsrelevantes Thema erkannt — Freigabe erforderlich"
fi

if [ "$NEEDS_APPROVAL" = "true" ]; then
    log "FREIGABE ERFORDERLICH — Robert wird benachrichtigt, Issue wird zurueckgestellt"

    # Robert per Telegram informieren
    python3 "$TELEGRAM_SCRIPT" "🔐 *Freigabe erforderlich*

Issue #${ISSUE_NR}: ${ISSUE_TITLE}

Das Issue wurde als sicherheitsrelevant oder freigabepflichtig eingestuft.

➡ Bitte pruefen und freigeben: http://localhost:3000/meister/content-autopilot-v2/issues/${ISSUE_NR}

Label 'freigegeben' hinzufuegen um die Bearbeitung zu starten." 2>/dev/null || true

    # Issue kommentieren
    curl -sf -X POST "${GITEA_API}/issues/${ISSUE_NR}/comments?token=${GITEA_TOKEN}" \
        -H 'Content-Type: application/json' \
        -d "{\"body\": \"⏸ **Freigabe erforderlich**\\n\\nDieses Issue wurde als sicherheitsrelevant oder freigabepflichtig eingestuft.\\n\\nRobert wurde per Telegram benachrichtigt. Bitte Label \`freigegeben\` hinzufuegen um die Bearbeitung zu starten.\\n\\nInzwischen arbeite ich an anderen Issues.\"}" \
        >> "$LOGFILE" 2>&1 || true

    # Label 'wartet-auf-freigabe' setzen via Python (env-var Uebergabe)
    ISSUE_NR_VAL="$ISSUE_NR" python3 /opt/content-autopilot-v2/scripts/set_label.py \
        "wartet-auf-freigabe" "#FF6B6B" >> "$LOGFILE" 2>&1 || true

    log "Robert benachrichtigt, Issue ${ISSUE_NR} zurueckgestellt"
    exit 0
fi

# Normales Issue — Claude Agent starten
log "Starte Claude Agent fuer Issue #${ISSUE_NR}..."

PROMPT="Du bist der Fullstack-Vorarbeiter fuer Content Autopilot v2.

AKTUELLES ISSUE #${ISSUE_NR}:
Titel: ${ISSUE_TITLE}
Body:
${ISSUE_BODY}

DEIN WORKFLOW (ZWINGEND):

## Schritt 1: Research & Validierung (vor jeder Implementierung!)
Bevor du code schreibst, recherchiere den Stand der Technik:
- Nutze WebSearch fuer das Thema des Issues
- Suche nach wissenschaftlichen Papers, offiziellen Docs, etablierten Patterns
- Validiere deinen Ansatz mit mindestens 2 hochwertigen Quellen
- Dokumentiere die Quellen als Kommentar im Issue BEVOR du implementierst
- Keine Traumschlösser: Nur was nachweislich funktioniert und skaliert

Beispiel-Suchbegriffe je nach Thema:
- Performance: 'site:web.dev OR site:developer.mozilla.org <thema>'
- Algorithmus: '<algorithmus name> research paper 2023 2024 2025'
- Best Practice: '<framework> <pattern> official documentation'

## Schritt 2: Ansatz dokumentieren
Kommentiere auf Issue #${ISSUE_NR}:
- Was wirst du bauen (1-2 Saetze)
- Quellen die deinen Ansatz validieren (mit URL)
- Abgrenzung: Was machst du NICHT (Scope-Control)

## Schritt 3: Implementierung (PDCA)
- PLAN: Branch erstellen (git checkout -b feature/issue-${ISSUE_NR}-kurzbeschreibung)
- DO: Feature bauen, dabei CLAUDE.md Grenzen einhalten
- CHECK: Tests ausfuehren (siehe CLAUDE.md Teststufen)
- ACT: Commit + Push + Issue kommentieren + schliessen

## Schritt 4: Self-Learning Update
Nach erfolgreicher Implementierung:
- Pruefe ob eine neue Erkenntnis in CLAUDE.md aufgenommen werden sollte
- Nur wirklich neue, nicht-offensichtliche Erkenntnisse (z.B. ein gotcha, ein Pattern das funktioniert hat)
- Ergaenze CLAUDE.md Abschnitt '## Gelernte Patterns' falls sinnvoll
- Commit den CLAUDE.md Update mit: 'chore: update CLAUDE.md learnings from #${ISSUE_NR}'

## Schritt 5: Naechstes Issue
Nach Abschluss: offene Issues pruefen und weiterarbeiten bis keine mehr offen sind.

WICHTIG: Lies zuerst /opt/content-autopilot-v2/CLAUDE.md fuer alle Grenzen und Konventionen!"

# Start-Notification
python3 "$TELEGRAM_SCRIPT" "🤖 *Content Autopilot Agent gestartet*

Issue #${ISSUE_NR}: ${ISSUE_TITLE}

Ich arbeite jetzt daran — Research, Implementierung, Tests.
Melde mich wenn fertig." 2>/dev/null || true

# Claude im Hintergrund starten (non-interactive, mit Permission-Bypass)
cd /opt/content-autopilot-v2
claude --dangerously-skip-permissions --print \
    "$PROMPT" \
    >> "$LOGFILE" 2>&1

EXIT_CODE=$?
log "Claude Agent beendet mit Exit-Code: ${EXIT_CODE}"

if [ $EXIT_CODE -eq 0 ]; then
    log "Issue #${ISSUE_NR} erfolgreich abgearbeitet"
    python3 "$TELEGRAM_SCRIPT" "✅ *Issue #${ISSUE_NR} erledigt*

${ISSUE_TITLE}

Deployed und getestet. Log: ${LOGFILE}" 2>/dev/null || true
else
    log "FEHLER beim Abarbeiten von Issue #${ISSUE_NR} — Log: ${LOGFILE}"
    python3 "$TELEGRAM_SCRIPT" "⚠️ Issue Agent Fehler

Issue #${ISSUE_NR}: ${ISSUE_TITLE}
Exit-Code: ${EXIT_CODE}

Log: ${LOGFILE}" 2>/dev/null || true
fi
