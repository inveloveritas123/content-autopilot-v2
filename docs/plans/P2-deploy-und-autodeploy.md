# P2 — content-truth Deploy (Bind-Mount) + Auto-Deploy via GitHub Actions

**Status:** Plan (Konzept, noch nicht umgesetzt)
**Datum:** 2026-06-11
**Bezug:** `content-truth/{prompts,rules,schemas}/`, `docker-compose.v2.yml`, `setup.sh`,
`backend/config.py` (`content_truth_base_path`, `prompt_storage_backend`),
`backend/services/local_fs_storage.py`, `backend/services/prompt_loader.py`

**Constraints (aus CLAUDE.md, gelten für alles hier):**

- Nur Ports **8601** (nginx) und **8180** (MCP) — dieser Plan belegt **keine** neuen Ports.
- **Keine** Firewall-/UFW-, systemd- oder PostgreSQL-Config-Änderungen.
- v1 unter `/opt/zukunftsbund-content-autopilot/` wird **nicht** angefasst.
- Proxmox-LXC: alle Container brauchen `privileged: true` + `security_opt: [label=disable]` (bereits so in `docker-compose.v2.yml`).
- Frontend wird **auf dem Host** gebaut (npm/esbuild funktioniert im Docker auf diesem LXC nicht).
- Gitea ist stillgelegt — **GitHub `inveloveritas123/content-autopilot-v2` ist Source of Truth.**

---

## (a) Bind-Mount: `content-truth/` in die Container

### Ist-Zustand

- `backend/config.py` hat bereits `prompt_storage_backend: str = "localfs"` und
  `content_truth_base_path: str = "/app/content-truth"`.
- `get_default_storage_adapter()` (in `backend/services/brand_voice_storage.py`) liefert
  defaultmäßig einen `LocalFsStorageAdapter(base_dir="/app/content-truth")`.
- Der `PromptLoader` (`backend/services/prompt_loader.py`) liest relative Pfade wie
  `prompts/P01-kundenkontext-extraktion.md` und `rules/hookmaster.md` über diesen Adapter —
  exakt das Layout von `content-truth/`.
- **Aber:** In `docker-compose.v2.yml` ist `content-truth/` bisher **nirgends gemountet**.
  Nur `backend-v2` hat überhaupt ein Volume (`./data:/app/data`). Worker und Beat haben keins.
  → Prompt-Loads laufen im Container heute ins Leere (`StorageError`), sofern der Ordner
  nicht zufällig ins Image kopiert wurde.

### Wer braucht den Mount?

| Service | Braucht `content-truth/`? | Warum |
|---|---|---|
| `backend-v2` | **Ja** | API-Endpunkte, die Prompts/Schemas lesen (z. B. Voice-Profile, md_converter) |
| `celery-worker-v2` | **Ja** | P01/P03/P04/P12-Tasks laden Prompts via `PromptLoader` |
| `celery-beat-v2` | **Ja** (defensiv) | Gleiches Image/gleicher Code; Beat selbst lädt keine Prompts, aber identische Mounts halten die drei Backend-Container homogen und vermeiden Drift |
| `mcp-server-v2` | Nein | Spricht nur HTTP gegen `backend-v2` |
| `nginx-v2`, `redis-v2` | Nein | — |

### Diff-Skizze gegen `docker-compose.v2.yml`

Konventionen aus der echten Datei übernommen (Service-Namen `*-v2`, relative Host-Pfade
wie `./data`, `read_only: true` Container):

```diff
   backend-v2:
     ...
     environment:
       ...
+      # Kanonische Prompt/Rule/Schema-Quelle (Repo-Verzeichnis content-truth/)
+      CONTENT_TRUTH_BASE_PATH: ${CONTENT_TRUTH_BASE_PATH:-/app/content-truth}
       UVICORN_LOOP: asyncio
       ...
     volumes:
       - ./data:/app/data
+      - ./content-truth:/app/content-truth:ro
     networks:
       - cap-v2-net

   celery-worker-v2:
     ...
     environment:
       ...
+      CONTENT_TRUTH_BASE_PATH: ${CONTENT_TRUTH_BASE_PATH:-/app/content-truth}
+    volumes:
+      - ./content-truth:/app/content-truth:ro
     depends_on:
       redis-v2:
         condition: service_healthy

   celery-beat-v2:
     ...
     environment:
       ...
+      CONTENT_TRUTH_BASE_PATH: ${CONTENT_TRUTH_BASE_PATH:-/app/content-truth}
+    volumes:
+      - ./content-truth:/app/content-truth:ro
     depends_on:
       redis-v2:
         condition: service_healthy
```

**Entscheidung `:ro` (read-only):**

- `content-truth/` ist git-verwaltet; Änderungen gehören in Commits, nicht in
  Runtime-Writes. Ein `:ro`-Mount macht das technisch durchsetzbar.
- Der `LocalFsStorageAdapter` *kann* schreiben (atomar via mkstemp + `os.replace`).
  Mit `:ro` schlägt jeder solche Write mit `StorageError` fehl — **gewollt**, denn ein
  Container-Write würde beim nächsten `git pull` zu Konflikten führen.
- Falls sich später ein legitimer Write-Pfad herausstellt (z. B. Back-Sync von kuratierten
  Profilen), lieber ein separates beschreibbares Verzeichnis (`./data`) nutzen statt den
  `:ro` zu lockern.

**Proxmox-LXC-Eigenheiten (beachtet):**

1. Bind-Mounts vom LXC-Dateisystem in Docker-Container funktionieren auf diesem Host
   bereits (`./data:/app/data` läuft produktiv) — kein neues Risiko.
2. `security_opt: [label=disable]` ist gesetzt → **keine** SELinux-Relabel-Flags
   (`:z`/`:Z`) nötig oder erwünscht.
3. `read_only: true` der Container bleibt unangetastet; ein zusätzlicher Bind-Mount ist
   damit kompatibel (Mount-Punkte sind vom Container-rootfs unabhängig).
4. **Stolperfalle:** Existiert `./content-truth` auf dem Host *nicht*, legt Docker es
   stillschweigend als leeres root-eigenes Verzeichnis an → Container startet, Prompts
   fehlen trotzdem. Gegenmittel: Validierung in `setup.sh` (siehe unten) und der
   Health-/Fehlerpfad des `PromptLoader` (wirft hart, kein Stale-Fallback).
5. Kein `privileged`/`security_opt`-Change nötig — wir ändern nur `volumes:` +
   `environment:`.

---

## (b) Seed/Defaults: Der Mount IST der Seed

`content-truth/` liegt **im Repo** (`content-autopilot-v2/content-truth/` mit
13 Prompts, 2 Rules, 4 Schemas — identisch mit Louis' Phase-1-Ständen, per Diff
verifiziert). Damit gilt:

1. **Frischer Deploy:** `git clone` von GitHub bringt `content-truth/` automatisch mit.
   `bash setup.sh` startet den Stack, der Bind-Mount zeigt auf das geklonte Verzeichnis —
   **kein separater Seed-Schritt, kein Nextcloud-Abhängigkeit.** (Der NC-Adapter bleibt
   als `prompt_storage_backend: "nc"` deprecated-Fallback konfigurierbar.)
2. **Updates:** `git pull` auf dem Server aktualisiert die Dateien *in place*. Der
   `PromptLoader` cached mit TTL = 300 s **plus mtime-Check via `stat()`** — geänderte
   Prompts werden also ohne Container-Restart spätestens nach Cache-Ablauf, bei
   mtime-Änderung sofort beim nächsten `load()`, wirksam. Kein Rebuild nötig, weil die
   Dateien gemountet (nicht ins Image gebacken) sind.
3. **Mount leer/fehlt (Fehlerbild):**
   - `PromptLoader.load()` → `LocalFsStorageAdapter.read()` → `StorageError`
     („Lesen fehlgeschlagen") wird **direkt re-raised** — bewusst kein Stale-Fallback
     (Kommentar im Code). Der jeweilige Celery-Task bzw. API-Call schlägt laut und
     eindeutig fehl; es wird **nie** mit falschen/leeren Prompts generiert.
   - `md_converter.py` wirft bei fehlendem `p03_output_schema.json` bereits eine
     sprechende Fehlermeldung („Stellen Sie sicher, dass … deployed ist").
   - **Ergänzung (empfohlen):** In `setup.sh` einen Preflight-Check aufnehmen, analog
     zur `.env`-Validierung:

     ```bash
     # STEP X: content-truth Preflight
     for f in prompts/P01-kundenkontext-extraktion.md rules/hookmaster.md schemas/p01.schema.json; do
         [ -f "${SCRIPT_DIR}/content-truth/${f}" ] \
             || die "content-truth/${f} fehlt" "git pull ausführen — content-truth/ ist Teil des Repos"
     done
     ```

4. **`content_truth_base_path` setzen:**
   - Default ist bereits im Code: `content_truth_base_path: str = "/app/content-truth"`
     (`backend/config.py:41`), gelesen via pydantic-settings → env-Variable
     `CONTENT_TRUTH_BASE_PATH` überschreibt bei Bedarf.
   - Normalfall: **nichts setzen** — Compose-Mount-Ziel und Code-Default stimmen überein.
   - Die Diff-Skizze oben exponiert `CONTENT_TRUTH_BASE_PATH: ${CONTENT_TRUTH_BASE_PATH:-/app/content-truth}`
     nur der Sichtbarkeit/Overridebarkeit halber (z. B. für lokale Dev-Setups ohne Docker).
   - `.env.example` um einen auskommentierten Eintrag ergänzen:
     `# CONTENT_TRUTH_BASE_PATH=/app/content-truth` (Default, i. d. R. nicht ändern).

---

## (c) Auto-Deploy: GitHub Actions → Server B

### Zielablauf

```
push auf main
  ├─ CI: "Tests (pytest)"  (tests.yml)        ─┐
  ├─ CI: "Lint (ruff + eslint + prettier)"     ├─ beide grün?
  └─ ... (weitere Workflows, nicht gate-relevant)
                                               ▼
                       deploy.yml (workflow_run-Trigger)
                         ├─ Gate-Job: prüft Tests UND Lint für den head_sha
                         └─ Deploy-Job: SSH → 152.53.142.163:10022 (meister)
                              cd /opt/content-autopilot-v2
                              git pull --ff-only
                              Frontend auf HOST bauen (npm ci && npm run build)
                              docker compose build backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2
                              docker compose up -d --force-recreate <dieselben Services>
                              docker compose restart nginx-v2   # IP-Cache! (gelerntes Pattern)
                              Health-Check :8601/api/health
```

Designentscheidungen:

- **`workflow_run` statt `needs:`**, weil Tests und Lint bestehende, separate Workflows
  sind, die wir nicht umbauen wollen. `workflow_run` feuert pro abgeschlossenem Workflow —
  deshalb prüft ein Gate-Job per `gh api`, ob **beide** Pflicht-Workflows für denselben
  `head_sha` erfolgreich sind (sonst no-op; der „letzte" grüne Workflow löst dann das
  Deploy aus). `concurrency` verhindert Doppel-Deploys.
- **Frontend-Build gehört ins Deploy-Skript auf dem Host** (LXC-Constraint: npm im
  Docker geht nicht; `nginx/Dockerfile.v2` verpackt das gebaute `frontend/dist`).
- **`restart nginx-v2` nach dem Recreate** wegen des dokumentierten nginx-IP-Cache-Problems
  (Gelerntes Pattern, Issue #37): Backend-Recreate ändert die Container-IP, nginx cached sie.
- `content-truth/`-Änderungen brauchen wegen des Bind-Mounts **keinen** Build — `git pull`
  reicht; der Build-Schritt schadet aber nicht (Cache-Hit) und hält den Workflow einfach.
- Kein `docker compose down`, kein Stack-Neustart von `redis-v2`/`mcp-server-v2`/Nextcloud —
  nur die betroffenen Services. v1 (:8501) bleibt unberührt.

### Vorschlag `.github/workflows/deploy.yml` (vollständig — NICHT in diesem Schritt anlegen)

```yaml
name: Deploy (Server B)

# Deployt main auf Server B (/opt/content-autopilot-v2), NACHDEM die bestehende
# CI gruen ist. Trigger: workflow_run der beiden Pflicht-Workflows; ein Gate-Job
# verifiziert, dass BEIDE fuer denselben Commit erfolgreich waren.
#
# Constraints (CLAUDE.md): nur Ports 8601/8180, keine Firewall-/systemd-/
# Postgres-Aenderungen, v1 unter /opt/zukunftsbund-content-autopilot/ tabu.
# Dieses Deploy beruehrt ausschliesslich /opt/content-autopilot-v2.

on:
  workflow_run:
    workflows:
      - "Tests (pytest)"
      - "Lint (ruff + eslint + prettier)"
    types: [completed]
    branches: [main]
  workflow_dispatch: {}   # manueller Notfall-/Erst-Deploy

concurrency:
  group: deploy-server-b
  cancel-in-progress: false   # laufendes Deploy nie hart abbrechen

permissions:
  contents: read
  actions: read   # fuer den CI-Gate-Check via gh api

jobs:
  gate:
    name: CI-Gate (Tests + Lint gruen fuer diesen Commit?)
    runs-on: ubuntu-latest
    # workflow_run: nur weitermachen, wenn der ausloesende Lauf selbst gruen war
    if: >-
      github.event_name == 'workflow_dispatch' ||
      (github.event.workflow_run.conclusion == 'success' &&
       github.event.workflow_run.head_branch == 'main')
    outputs:
      ready: ${{ steps.check.outputs.ready }}
      sha: ${{ steps.check.outputs.sha }}
    steps:
      - name: Beide Pflicht-Workflows fuer head_sha pruefen
        id: check
        env:
          GH_TOKEN: ${{ github.token }}
          SHA: ${{ github.event.workflow_run.head_sha || github.sha }}
        run: |
          set -euo pipefail
          ready=true
          for wf in tests.yml lint.yml; do
            conclusion=$(gh api \
              "repos/${GITHUB_REPOSITORY}/actions/workflows/${wf}/runs?head_sha=${SHA}&status=completed&per_page=1" \
              --jq '.workflow_runs[0].conclusion // "pending"')
            echo "${wf}: ${conclusion}"
            if [ "${conclusion}" != "success" ]; then ready=false; fi
          done
          echo "ready=${ready}" >> "$GITHUB_OUTPUT"
          echo "sha=${SHA}" >> "$GITHUB_OUTPUT"

  deploy:
    name: Deploy auf Server B
    needs: gate
    if: needs.gate.outputs.ready == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    environment: production   # optional: Schutzregeln/Required Reviewers in GitHub
    steps:
      - name: SSH-Key und known_hosts einrichten
        env:
          DEPLOY_SSH_KEY: ${{ secrets.DEPLOY_SSH_KEY }}
          DEPLOY_KNOWN_HOSTS: ${{ secrets.DEPLOY_KNOWN_HOSTS }}
        run: |
          set -euo pipefail
          mkdir -p ~/.ssh
          printf '%s\n' "${DEPLOY_SSH_KEY}" > ~/.ssh/deploy_key
          chmod 600 ~/.ssh/deploy_key
          printf '%s\n' "${DEPLOY_KNOWN_HOSTS}" > ~/.ssh/known_hosts
          chmod 644 ~/.ssh/known_hosts

      - name: Remote-Deploy ausfuehren
        env:
          DEPLOY_HOST: ${{ secrets.DEPLOY_HOST }}   # 152.53.142.163
          DEPLOY_PORT: ${{ secrets.DEPLOY_PORT }}   # 10022
          DEPLOY_USER: ${{ secrets.DEPLOY_USER }}   # meister
          TARGET_SHA: ${{ needs.gate.outputs.sha }}
        run: |
          set -euo pipefail
          ssh -i ~/.ssh/deploy_key \
              -p "${DEPLOY_PORT}" \
              -o StrictHostKeyChecking=yes \
              -o ConnectTimeout=15 \
              "${DEPLOY_USER}@${DEPLOY_HOST}" \
              "TARGET_SHA='${TARGET_SHA}' bash -s" <<'REMOTE'
          set -euo pipefail
          cd /opt/content-autopilot-v2

          echo "=== 1/6 Git-Update (GitHub = Source of Truth) ==="
          git fetch origin main
          git checkout main
          git merge --ff-only "${TARGET_SHA:-origin/main}"
          # content-truth/ ist damit bereits aktualisiert (Bind-Mount, kein Build noetig)

          echo "=== 2/6 Frontend auf dem HOST bauen (LXC: npm im Docker geht nicht) ==="
          cd frontend
          npm ci
          npm run build
          cd ..

          echo "=== 3/6 Images bauen (nur betroffene Services) ==="
          docker compose -f docker-compose.v2.yml build \
            backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2

          echo "=== 4/6 Services neu erstellen ==="
          docker compose -f docker-compose.v2.yml up -d --force-recreate \
            backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2

          echo "=== 5/6 nginx restart (IP-Cache nach Backend-Recreate) ==="
          docker compose -f docker-compose.v2.yml restart nginx-v2

          echo "=== 6/6 Health-Check ==="
          for i in $(seq 1 30); do
            if curl -sf http://localhost:8601/api/health > /dev/null; then
              echo "Health OK (Versuch ${i})"
              exit 0
            fi
            sleep 5
          done
          echo "Health-Check fehlgeschlagen — letzte Backend-Logs:" >&2
          docker compose -f docker-compose.v2.yml logs backend-v2 --tail 50 >&2
          exit 1
          REMOTE
```

### Benötigte GitHub-Secrets

| Secret | Wert | Zweck |
|---|---|---|
| `DEPLOY_SSH_KEY` | privater ed25519-Key (nur für Deploy erzeugt) | SSH-Auth |
| `DEPLOY_HOST` | `152.53.142.163` | Zieladresse (als Secret, nicht hardcoded) |
| `DEPLOY_PORT` | `10022` | SSH-Port |
| `DEPLOY_USER` | `meister` | SSH-User |
| `DEPLOY_KNOWN_HOSTS` | Output von `ssh-keyscan` (s. u.) | Host-Key-Pinning statt TOFU |

### Einmalige manuelle Schritte (Setup)

```bash
# 1) Deploy-Key erzeugen (lokal oder auf einem Admin-Rechner, NICHT committen)
ssh-keygen -t ed25519 -C "github-actions-deploy@content-autopilot-v2" \
  -f ./deploy_key -N ""

# 2) Public Key auf Server B autorisieren (als meister)
#    Optional haerten mit from=/command= — restrict verbietet Forwarding etc.
cat deploy_key.pub | ssh -p 10022 meister@152.53.142.163 \
  'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
#    Empfohlene authorized_keys-Zeile (Key-Optionen voranstellen):
#    restrict,pty ssh-ed25519 AAAA... github-actions-deploy@content-autopilot-v2

# 3) Host-Key fuer Pinning erfassen
ssh-keyscan -p 10022 152.53.142.163 > known_hosts_entry.txt

# 4) Secrets in GitHub eintragen (Repo inveloveritas123/content-autopilot-v2
#    → Settings → Secrets and variables → Actions):
#    DEPLOY_SSH_KEY   = Inhalt von ./deploy_key (PRIVATER Key)
#    DEPLOY_HOST      = 152.53.142.163
#    DEPLOY_PORT     = 10022
#    DEPLOY_USER      = meister
#    DEPLOY_KNOWN_HOSTS = Inhalt von known_hosts_entry.txt
#    (alternativ per CLI: gh secret set DEPLOY_SSH_KEY < deploy_key  usw.)

# 5) Lokale Key-Dateien sicher loeschen
rm -f deploy_key deploy_key.pub known_hosts_entry.txt

# 6) Auf dem Server pruefen, dass origin auf GitHub zeigt (Gitea ist tot):
ssh -p 10022 meister@152.53.142.163 \
  'cd /opt/content-autopilot-v2 && git remote -v'
#    Falls noetig: git remote set-url origin git@github.com:inveloveritas123/content-autopilot-v2.git
#    (oder https mit Deploy-Token zum PULLEN — der Actions-Workflow pusht nie auf den Server-Checkout)

# 7) Erst-Deploy manuell ausloesen: Actions → "Deploy (Server B)" → Run workflow
```

### Offene Voraussetzung / Risiko (explizit KEIN Teil dieses Plans)

- **Erreichbarkeit von Port 10022 für GitHub-Runner:** v2-App-Ports (8601/8180) sind
  VPN-only; SSH 10022 wird heute administrativ genutzt. Falls UFW 10022 für das
  öffentliche Internet blockt, kann der GitHub-gehostete Runner den Server nicht
  erreichen. **Wir ändern gemäß Constraints KEINE Firewall-Regeln.** Optionen, die
  Robert dann entscheiden muss:
  1. 10022 ist bereits öffentlich erreichbar (wahrscheinlich, da Admin-Zugang) → nichts zu tun.
  2. Self-hosted GitHub-Runner *im Projektverzeichnis* auf Server B (läuft als
     User-Prozess/Container, kein systemd-Service nötig) → Deploy-Job mit
     `runs-on: self-hosted`, SSH entfällt komplett.
  3. Manuelles Freischalten von 10022 für GitHubs IP-Ranges (Firewall-Änderung →
     laut CLAUDE.md „Sofort stoppen + Robert" — nur durch Robert selbst).
- Weitere Workflows (`e2e-smoke.yml`, `security-tests.yml`, …) sind bewusst **nicht**
  Teil des Gates (Stabilität); Erweiterung des Gates = eine Zeile in der `for wf in`-Schleife.

### Rollback

```bash
ssh -p 10022 meister@152.53.142.163
cd /opt/content-autopilot-v2
git log --oneline -5                      # letzten guten Stand finden
git checkout <good-sha>                   # detached ist ok fuer Hotfix-Rollback
cd frontend && npm ci && npm run build && cd ..
docker compose -f docker-compose.v2.yml build backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2
docker compose -f docker-compose.v2.yml up -d --force-recreate backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2
docker compose -f docker-compose.v2.yml restart nginx-v2
```

(DB-Migrationen sind davon unabhängig — siehe Risiken in `P4-schema-realignment.md`,
Alembic-Downgrades nur additiv-revertierbar planen.)
