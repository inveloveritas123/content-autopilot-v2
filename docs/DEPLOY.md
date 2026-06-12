# Deploy-Dokumentation — content-autopilot-v2

Dieses Dokument beschreibt, wie content-autopilot-v2 auf Server B deployt wird —
sowohl manuell als auch automatisch via GitHub Actions.

> **Kurz-Referenz:** Server B ist `152.53.142.163`, Port `10022`, User `meister`,
> Projektverzeichnis `/opt/content-autopilot-v2`.

---

## Wie deployt wird

### Automatisches Deploy (Normalfall)

Jeder Merge auf `main` loest automatisch einen Deploy aus, **sobald beide
Pflicht-CI-Workflows gruen sind**:

```
push → main
  ├─ Tests (pytest)          ─┐
  └─ Lint (ruff + eslint)    ─┴─ beide gruen?
                                      ↓
                        deploy.yml (workflow_run)
                          Gate-Job: prueft Tests + Lint fuer denselben SHA
                          Deploy-Job: SSH → Server B
```

Was der Deploy-Job auf dem Server ausfuehrt (in dieser Reihenfolge):

1. `git fetch origin main && git merge --ff-only <sha>` — holt den Commit,
   inkl. `content-truth/` (kein separater Schritt noetig)
2. `cd frontend && npm ci && npm run build` — Frontend auf dem Host bauen
   (npm/esbuild funktioniert im Docker auf diesem LXC nicht)
3. `docker compose -f docker-compose.v2.yml build backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2`
4. `docker compose -f docker-compose.v2.yml up -d --force-recreate <dieselben Services>`
5. `docker compose -f docker-compose.v2.yml restart nginx-v2` — Pflicht wegen
   nginx-IP-Cache (Backend-Recreate aendert Container-IP, nginx cached sie)
6. Health-Check `curl -sf http://localhost:8601/api/health` (30 Versuche, je 5s)

`redis-v2`, `mcp-server-v2` und der optionale Nextcloud-Stack werden nicht
angefasst. v1 unter `/opt/zukunftsbund-content-autopilot/` bleibt unberuehrt.

### Manueller Deploy (Notfall / Erst-Deploy)

Der Workflow-Gate-Check laeuft auch bei `workflow_dispatch` — Deploy wird NICHT ausgeloest,
solange Tests oder Lint fuer HEAD fehlschlagen. Einziger Ausweg bei defektem CI: **direkter
SSH-Zugang zum Server** (siehe Notfall-/Rollback-Abschnitt unten).

```bash
# Versuch, Workflow manuell auszuloesen:
# (wird aber unterbrochen, falls CI fehlschlaegt)
gh workflow run deploy.yml --ref main

# Im echten Notfall (CI irreparabel): direkt auf dem Server arbeiten
ssh -p 10022 meister@152.53.142.163
cd /opt/content-autopilot-v2
git pull --ff-only
cd frontend && npm ci && npm run build && cd ..
docker compose -f docker-compose.v2.yml build backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2
docker compose -f docker-compose.v2.yml up -d --force-recreate backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2
docker compose -f docker-compose.v2.yml restart nginx-v2
curl -sf http://localhost:8601/api/health
```

---

## content-truth — Source of Truth fuer Prompts

`content-truth/` im Repo-Root (Unterverzeichnisse `prompts/`, `rules/`, `schemas/`)
ist die kanonische Quelle aller Prompt-Templates, Rules und Output-Schemas. Das
Verzeichnis wird als **Bind-Mount** (read-only) in die Container gehaengt:

```
./content-truth  →  /app/content-truth:ro   (backend-v2, celery-worker-v2, celery-beat-v2)
```

Das bedeutet:

- `git pull` auf dem Server aktualisiert Prompts **ohne** Container-Rebuild.
  Der `PromptLoader` cached mit TTL + mtime-Check; geaenderte Dateien wirken
  spaetestens nach Cache-Ablauf.
- Der Mount ist `:ro` (read-only). Runtime-Writes in den Container schlagen
  bewusst fehl — Prompt-Aenderungen gehoeren in Git-Commits, nicht in
  Container-Zustand.
- `setup.sh` prueft vor dem Stack-Start, ob `content-truth/prompts/` existiert
  und nicht leer ist. Docker wuerde sonst stumm ein leeres Verzeichnis anlegen.

### Overlay fuer Prompt-Studio-Edits (P3)

Das Prompt-Studio ermoegliche es, Prompts, Rules und Schemas direkt ueber
die Web-UI zu bearbeiten — ohne Container-Rebuild und ohne den `:ro`-Mount
von `content-truth` zu aendern.

Schreibzugriff erfolgt ueber ein **beschreibbares Overlay**:

```
./data/prompts-custom/  →  /app/data/prompts-custom   (backend-v2, celery-worker-v2, celery-beat-v2)
```

**Lese-Semantik: Overlay-first, Fallback auf Base (content-truth).**
Das Overlay-Verzeichnis wird automatisch angelegt wenn ein erster Save
ueber die Prompt-Studio-UI durchgefuehrt wird.

Das Overlay ist via `.gitignore` (Zeile `data/`) vom Git-Repository
ausgeschlossen — kein Konflikt mit `git pull`.

**Wichtige Hinweise fuer den Betrieb:**

- Nach einem `git pull` mit Prompt-Aenderungen in `content-truth`:
  Overlay-Dateien fuer die geaenderten Prompts pruefen und ggf. reverten
  (Prompt-Studio → „Auf Base zuruecksetzen"). Sonst ist die Base-Version
  unsichtbar — das Overlay gewinnt dauerhaft.
- Deploy-Check nach Neustart: `docker compose exec celery-worker-v2 ls /app/data/prompts-custom`
  — ohne den `./data`-Mount sehen Worker Overlay-Edits nicht.
- Overlays sind nicht git-versioniert. Das Audit-Log (Container-Logs, JSON)
  enthaelt sha-Hashes aller Saves.

**ENV:**
```
CONTENT_TRUTH_OVERLAY_PATH=${CONTENT_TRUTH_OVERLAY_PATH:-/app/data/prompts-custom}
```

Alle drei Services (`backend-v2`, `celery-worker-v2`, `celery-beat-v2`) haben
diesen Mount und diese ENV bereits in `docker-compose.v2.yml` eingetragen.

---

## Einmalige Einrichtung: GitHub-Secrets setzen

### Schritt-fuer-Schritt

**1. Deploy-Key erzeugen** (lokal, NICHT committen):

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy@content-autopilot-v2" \
  -f ./deploy_key -N ""
# Erzeugt: ./deploy_key (privat) und ./deploy_key.pub (oeffentlich)
```

**2. Public Key auf Server B autorisieren** (als User `meister`):

```bash
cat deploy_key.pub | ssh -p 10022 meister@152.53.142.163 \
  'mkdir -p ~/.ssh && chmod 700 ~/.ssh && \
   cat >> ~/.ssh/authorized_keys && \
   chmod 600 ~/.ssh/authorized_keys'
```

Empfohlene `authorized_keys`-Zeile (haertet den Key ab — verbietet
Port-Forwarding, Agent-Forwarding etc.):

```
restrict,pty ssh-ed25519 AAAA... github-actions-deploy@content-autopilot-v2
```

**3. Host-Key fuer DEPLOY_KNOWN_HOSTS erfassen**:

```bash
ssh-keyscan -p 10022 152.53.142.163 > known_hosts_entry.txt
# Inhalt pruefen (sieht aus wie: [152.53.142.163]:10022 ssh-ed25519 AAAA...)
cat known_hosts_entry.txt
```

**4. Secrets in GitHub eintragen**
(Repo `inveloveritas123/content-autopilot-v2` → Settings → Secrets and variables → Actions):

| Secret | Wert |
|---|---|
| `DEPLOY_SSH_KEY` | Inhalt von `./deploy_key` (privater Key, mehrzeilig) |
| `DEPLOY_HOST` | `152.53.142.163` |
| `DEPLOY_PORT` | `10022` |
| `DEPLOY_USER` | `meister` |
| `DEPLOY_KNOWN_HOSTS` | Inhalt von `known_hosts_entry.txt` |

Alternativ per CLI:

```bash
gh secret set DEPLOY_SSH_KEY < deploy_key
gh secret set DEPLOY_HOST --body "152.53.142.163"
gh secret set DEPLOY_PORT --body "10022"
gh secret set DEPLOY_USER --body "meister"
gh secret set DEPLOY_KNOWN_HOSTS < known_hosts_entry.txt
```

**5. Lokale Key-Dateien loeschen**:

```bash
rm -f deploy_key deploy_key.pub known_hosts_entry.txt
```

**6. Git-Remote auf Server B pruefen** (muss auf GitHub zeigen, nicht Gitea):

```bash
ssh -p 10022 meister@152.53.142.163 \
  'cd /opt/content-autopilot-v2 && git remote -v'
# Falls noetig:
# git remote set-url origin git@github.com:inveloveritas123/content-autopilot-v2.git
```

**7. Erst-Deploy manuell ausloesen**:

```bash
gh workflow run deploy.yml --ref main
# oder: GitHub → Actions → "Deploy (Server B)" → Run workflow
```

---

## Rollback

```bash
ssh -p 10022 meister@152.53.142.163
cd /opt/content-autopilot-v2

# Letzten guten Stand finden:
git log --oneline -5

# Auf bekannt-guten Commit zurueck (detached HEAD ist ok fuer Hotfix-Rollback):
git checkout <good-sha>

# Frontend und Services neu bauen:
cd frontend && npm ci && npm run build && cd ..
docker compose -f docker-compose.v2.yml build \
  backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2
docker compose -f docker-compose.v2.yml up -d --force-recreate \
  backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2
docker compose -f docker-compose.v2.yml restart nginx-v2

# Verifizieren:
curl -sf http://localhost:8601/api/health
```

Danach auf `main` zurueck:

```bash
git checkout main
git pull --ff-only
```

> **Hinweis zu Datenbank-Migrationen:** Alembic-Downgrades sind nur moeglich,
> wenn die Migrationen als additiv-revertierbar geplant sind (keine DROP COLUMN
> in upgrade). Im Zweifelsfall Rollback nur nach DB-Backup.

---

## Offene Voraussetzung: SSH-Erreichbarkeit fuer GitHub-Runner

Port 10022 wird heute administrativ genutzt. Falls UFW diesen Port nur fuer
das VPN freigibt, koennen GitHub-gehostete Runner den Server nicht erreichen.

Optionen (Entscheidung bei Robert):

1. Port 10022 ist bereits oeffentlich erreichbar → nichts zu tun.
2. Self-hosted GitHub-Runner auf Server B (laeuft als User-Prozess, kein
   systemd-Service noetig) → `runs-on: self-hosted` in `deploy.yml`, SSH
   entfaellt. Kein Firewall-Eingriff noetig.
3. 10022 fuer GitHub-IP-Ranges freischalten (UFW-Aenderung → laut CLAUDE.md
   sofort stoppen und Robert informieren; nur durch Robert selbst).
