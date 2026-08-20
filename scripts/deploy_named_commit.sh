#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Content Autopilot v2 — Deploy eines BENANNTEN Commits, mit Verify.
#
# Verhindert strukturell die Renn-Luecke aus SSOT-LOUIS-KETTE-KORREKT-2026-08-21
# §0: dort wurde "der aktuelle Stand" deployt, waehrend parallel noch commitet
# wurde — der Container trug fuenf Minuten spaeter nicht mehr den Stand, der
# beim Absprung des Deploys "alles" war. Dieses Skript deployt IMMER einen
# expliziten SHA (kein "HEAD", kein "main"-Branchname zur Laufzeit aufgeloest)
# und verifiziert danach ueber /api/version, dass GENAU dieser SHA laeuft.
#
# Aufruf:
#   scripts/deploy_named_commit.sh <sha> <ssh-host> <ssh-port> <incus-container> <health-url>
#
# Beispiel (Testserver):
#   scripts/deploy_named_commit.sh d0be1c4 ingo@152.53.142.163 10022 \
#     content-autopilot http://localhost:8601/api/version
#
# Live braucht zusaetzlich die Traefik-Falle (docker restart traefik, beide
# -f-Dateien) — dieses Skript deckt den EINFACHEN Fall (ein -f, kein Traefik)
# ab, wie er auf dem Testserver gilt. Fuer Live siehe
# docs/DEPLOY-STAND-2026-08-14.md, Abschnitt "DEPLOY-FALLE AUF LIVE".
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1" >&2; }
info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

if [ $# -ne 5 ]; then
    fail "Aufruf: $0 <sha> <ssh-user@host> <ssh-port> <incus-container> <version-url>"
    exit 2
fi

SHA="$1"
SSH_TARGET="$2"
SSH_PORT="$3"
CONTAINER="$4"
VERSION_URL="$5"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# ─── 1. SHA auflösen und verifizieren, dass er existiert ─────────
cd "$REPO_ROOT"
RESOLVED_SHA="$(git rev-parse "$SHA")"
info "Deploye Commit $RESOLVED_SHA (angefordert: $SHA)"

# ─── 2. Archiv bauen, VERSION-Datei hinein — GENAU dieser SHA ────
ARCHIVE="$TMPDIR/deploy.tar"
git archive --format=tar -o "$ARCHIVE" "$RESOLVED_SHA"
echo -n "$RESOLVED_SHA" > "$TMPDIR/VERSION"
tar -rf "$ARCHIVE" -C "$TMPDIR" --transform 's,^,backend/,' VERSION
gzip -f "$ARCHIVE"
ARCHIVE="$ARCHIVE.gz"
ok "Archiv gebaut: $ARCHIVE (inkl. backend/VERSION = $RESOLVED_SHA)"

# ─── 3. Übertragen ────────────────────────────────────────────────
scp -i ~/.ssh/zukunftsbund-ops -P "$SSH_PORT" "$ARCHIVE" "$SSH_TARGET:/tmp/deploy-named-commit.tar.gz"
ok "Archiv uebertragen"

# ─── 4. Entpacken (nur bei bestätigter Incus-Erreichbarkeit) ──────
ssh -i ~/.ssh/zukunftsbund-ops -p "$SSH_PORT" "$SSH_TARGET" \
    "sudo incus file push /tmp/deploy-named-commit.tar.gz $CONTAINER/tmp/deploy-named-commit.tar.gz && \
     sudo incus exec $CONTAINER -- bash -c 'cd /opt/content-autopilot-v2 && tar -xzf /tmp/deploy-named-commit.tar.gz && rm /tmp/deploy-named-commit.tar.gz && test -f .env'"
ok "Entpackt, .env unberuehrt"

# ─── 5. Frontend + Backend/Celery/Nginx neu bauen ─────────────────
ssh -i ~/.ssh/zukunftsbund-ops -p "$SSH_PORT" "$SSH_TARGET" \
    "sudo incus exec $CONTAINER -- bash -c 'cd /opt/content-autopilot-v2/frontend && npm install && npm run build'"
ok "Frontend gebaut"

ssh -i ~/.ssh/zukunftsbund-ops -p "$SSH_PORT" "$SSH_TARGET" \
    "sudo incus exec $CONTAINER -- bash -c 'cd /opt/content-autopilot-v2 && docker compose -f docker-compose.v2.yml up -d --build backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2'"
ok "Backend/Celery/Nginx neu gebaut und gestartet"

# ─── 6+7. PFLICHT-VERIFY: /api/version direkt abfragen, mit Retry ─
# docker ps "healthy" ist KEIN verlaesslicher Vorbote — Nginx kann healthy
# melden, waehrend das frisch gestartete Backend dahinter noch nicht auf
# Requests antwortet (502 Bad Gateway, real beobachtet trotz 4/4 healthy).
# Deshalb direkt gegen /api/version pollen — das ist die Bedingung, die
# tatsaechlich zaehlt, nicht ein Zwischenschritt davor.
REMOTE_SHA=""
VERSION_RESPONSE=""
for _ in $(seq 1 24); do
    VERSION_RESPONSE="$(ssh -i ~/.ssh/zukunftsbund-ops -p "$SSH_PORT" "$SSH_TARGET" \
        "sudo incus exec $CONTAINER -- curl -s '$VERSION_URL'" || true)"
    REMOTE_SHA="$(echo "$VERSION_RESPONSE" | grep -oP '"commit_sha"\s*:\s*"\K[^"]+' || true)"
    if [ -n "$REMOTE_SHA" ]; then
        break
    fi
    sleep 5
done
if [ -z "$REMOTE_SHA" ]; then
    fail "Konnte nach 120s keine commit_sha aus /api/version lesen. Letzte Rohantwort: ${VERSION_RESPONSE:-<leer>}"
fi

if [ "$REMOTE_SHA" != "$RESOLVED_SHA" ]; then
    fail "VERIFY FEHLGESCHLAGEN: /api/version zeigt '$REMOTE_SHA', erwartet '$RESOLVED_SHA'"
    fail "Deploy gilt als NICHT erfolgt (SSOT AP2: Verify ist Teil des Deploys, nicht optional)."
    exit 1
fi

ok "VERIFIZIERT: /api/version zeigt exakt $RESOLVED_SHA"
