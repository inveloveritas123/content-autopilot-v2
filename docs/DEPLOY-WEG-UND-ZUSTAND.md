# Deploy-Weg & Zustand — content-autopilot.zukunftsbund.de

**Stand:** 2026-08-15 · Welle `zubu-deploy-bestand`
Alle Angaben gemessen, nicht aus Dokumentation übernommen.

---

## 1. ⛔ Welcher Server? Zwei Kisten, nicht verwechseln

| | **LIVE** | **ALT (nicht anfassen)** |
|---|---|---|
| Host | `128.140.67.21` | `152.53.142.163` |
| Name | `Content-Autopilot-Prod` | `kolonie-incus` (Proxmox/LXC) |
| Domain | **content-autopilot.zukunftsbund.de** | keine (DNS tot) |
| Zugang | `ssh -i ~/.ssh/zukunftsbund-ops ingo@128.140.67.21` | `ssh -p 10022 ingo@152.53.142.163` |
| Struktur | Docker direkt auf dem Host + Traefik | Incus-Container, darin Docker |
| Inhalt | Testsystem, **keine Kundendaten** | 2.765 Posts Tenant „ZKG" |
| GitHub-Runner | **keiner** | einer (`kolonie`) |

⚠️ **Der Registry-Eintrag nannte lange `152.53.142.163` und die Domains
`cap.`/`mcpcontent.zukunftsbund.de` — beide lösen im DNS nicht mehr auf.**
Das hat am 15.08. zu einer zweistündigen Fehlmessung geführt. Die richtige
Adresse steht in `~/orko/docs/runbooks/ZUKUNFTSBUND_SERVER_HAERTUNG_VOLLZUG.md`.

**Zuordnungsbeweis** (wiederholbar): Das ausgelieferte JS-Bundle vergleichen.
```bash
curl -s https://content-autopilot.zukunftsbund.de/ | grep -o 'assets/[^"]*\.js'
ssh … 'sudo docker exec content-autopilot-v2-nginx-v2-1 \
        grep -o "assets/[^\"]*\.js" /usr/share/nginx/html/index.html'
```
Stimmen sie überein, ist es der richtige Host.

---

## 2. ⛔ Deploy-Weg: MANUELL. Die GitHub-Kette zielt auf die falsche Kiste.

`.github/workflows/deploy.yml` nutzt `runs-on: [self-hosted, kolonie]`.
Dieser Runner läuft auf **`152.53.142.163`**. Auf dem Live-Server existiert
**kein Runner** (gemessen: kein Dienst, kein Prozess, kein Verzeichnis).

⛔ **Ein Push auf `main` würde grün melden und auf die ALTE Kiste deployen.**
Der Live-Server bliebe unverändert — ein stiller Fehldeploy.

### Der funktionierende Weg (am 15.08. vollzogen)

```bash
# 0. BACKUP — ohne Rückweg kein Eingriff
TS=$(date +%Y%m%d-%H%M%S)
ssh … 'sudo mkdir -p /opt/backup
        sudo -u postgres pg_dump -Fc content_autopilot_v2 -f /tmp/db.dump
        sudo mv /tmp/db.dump /opt/backup/cap-v2-vor-<name>-'$TS'.dump
        sudo tar czf /opt/backup/code-'$TS'.tar.gz -C /opt content-autopilot-v2
        sudo cp /opt/content-autopilot-v2/.env /opt/backup/env-'$TS

# 1. Stand lokal bauen, paketieren, übertragen
tar czf /tmp/stand.tar.gz --exclude=.git .
scp -i ~/.ssh/zukunftsbund-ops /tmp/stand.tar.gz ingo@128.140.67.21:/tmp/
ssh … 'rm -rf /tmp/neu && mkdir /tmp/neu && tar xzf /tmp/stand.tar.gz -C /tmp/neu'

# 2. ⛔ IMMER ERST TROCKENLAUF — siehe Falle 3.1
ssh … 'rsync -a --delete --dry-run --itemize-changes \
   --exclude=".git" --exclude="/.env" --exclude="/frontend/node_modules" \
   --exclude="/frontend/dist" --exclude="/data" \
   --exclude="/docker-compose.override.yml" \
   /tmp/neu/ /opt/content-autopilot-v2/ | grep "^\*deleting"'
# → NUR beabsichtigte Löschungen? Sonst STOPP.

# 3. Sync (gleiche Zeile ohne --dry-run)

# 4. Frontend auf dem HOST bauen (nicht in Docker)
ssh … 'cd /opt/content-autopilot-v2/frontend && npm ci && npm run build'

# 5. Images
ssh … 'cd /opt/content-autopilot-v2 && sudo docker compose \
   -f docker-compose.v2.yml build backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2'

# 6. Migration
ssh … 'sudo docker compose -f docker-compose.v2.yml run --rm backend-v2 alembic upgrade head'

# 7. ⛔ Neustart IMMER mit BEIDEN Compose-Dateien — siehe Falle 3.2
ssh … 'sudo docker compose -f docker-compose.v2.yml -f docker-compose.override.yml \
   up -d --force-recreate backend-v2 celery-worker-v2 celery-beat-v2 nginx-v2'

# 8. Verifikation gegen die DOMAIN, nicht gegen localhost
curl -s -o /dev/null -w "%{http_code}\n" https://content-autopilot.zukunftsbund.de/
curl -s https://content-autopilot.zukunftsbund.de/api/health
curl -s https://content-autopilot.zukunftsbund.de/ | grep -o 'assets/[^"]*\.js'   # neu?
```

---

## 3. ⛔⛔ Zwei Fallen, die beide am 15.08. zugeschnappt sind

### 3.1 `rsync --delete` löscht die Domain-Anbindung

`docker-compose.override.yml` liegt **nur auf dem Server** und ist **nicht im
Repo**. Sie enthält die Traefik-Router-Labels und das `traefik-public`-Netz —
also die gesamte Domain-Anbindung.

Ohne `--exclude=/docker-compose.override.yml` löscht `--delete` sie. Die Domain
wäre **dauerhaft** offline, und nach einem Rollback wäre die Ursache nicht mehr
auffindbar (die Datei ist ja in keinem Commit).

Am 15.08. vom Trockenlauf abgefangen. Kopie liegt unter
`/opt/backup/docker-compose.override.yml-20260815-112337`.

### 3.2 `-f docker-compose.v2.yml` allein schaltet die Override ab

Sobald `-f` explizit angegeben wird, lädt Docker Compose die
`docker-compose.override.yml` **nicht mehr automatisch**. Der nginx-Container
startet dann ohne Traefik-Labels und ohne `traefik-public`-Netz.

**Symptom: HTTP 404 auf der Domain**, obwohl alle Container „healthy" sind und
`localhost:8601` funktioniert.

Am 15.08. passiert — die Seite war ca. eine Minute offline.
**Fix: immer beide `-f` angeben.**

Prüfung:
```bash
sudo docker inspect content-autopilot-v2-nginx-v2-1 \
  -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
# MUSS enthalten: traefik-public
```

---

## 4. Zustand nach dem Deploy vom 15.08.

### Ausgelieferter Stand
`deploy/live-20260815` = Highlander `5970f69` + Auth-Fix (3 Commits)
+ PR #148 (WHERE-false) + 403-Teil aus PR #147.

### Dienste
| Container | Status |
|---|---|
| nginx-v2, backend-v2, celery-worker-v2, celery-beat-v2, redis-v2 | healthy |
| traefik | läuft (80/443, Let's Encrypt) |
| **mcp-server-v2** | ⛔ **Restart-Schleife** |

### Datenbank
- `content_autopilot_v2`, **Alembic `065 (head)`** (von 063 hochgezogen)
- **11 MB, keine Kundendaten** — 0 Posts, 0 Ideen, 0 Telegram-Verknüpfungen
- `users=3` (robert/louis/ingo, alle `owner`, alle aktiv)
- `agencies=1` („Zukunftsbund"), `tenants=1` („Default Tenant")
- **`user_tenant=3`** — am 15.08. geseedet, *das* war die Login-Ursache
- RLS: **43 Tabellen / 43 Policies** aktiv

### Login
Vor dem Seed sahen alle drei Benutzer **0 Tenants** → „Kein Zugang
eingerichtet". Nach dem Seed **3** (verifiziert per Query gegen die Live-DB).

---

## 5. Rückweg

```
/opt/backup/cap-v2-vor-highlander-20260815-112337.dump        (DB, 182K)
/opt/backup/code-vor-highlander-20260815-112337.tar.gz        (Code, 46M)
/opt/backup/env-vor-highlander-20260815-112337                (.env)
/opt/backup/docker-compose.override.yml-20260815-112337       (Domain-Anbindung)
```

DB zurück:
```bash
sudo -u postgres pg_restore -d content_autopilot_v2 --clean --if-exists \
     /opt/backup/cap-v2-vor-highlander-20260815-112337.dump
```

⚠️ Ein Code-Rollback allein reicht nicht: Migrationen `064`/`065` bleiben
angewandt. Beide sind additiv und per `alembic downgrade` revertierbar.

---

## 6. ⚠️ Was der Design-Token-Sweep NICHT war

Häufiges Missverständnis (Owner-Frage 15.08. zu `/ideas`):

**Die „Königswege"-Commits waren eine Token-Migration, kein Redesign.**
Commit `6edcc5a` ersetzte ausschließlich Farbklassen:
```diff
- color: 'bg-blue-100 text-blue-700'
+ color: 'bg-status-neu-bg text-status-neu-text'
```
Gleiche Farbwerte, nur benannt statt roh. **Layout, Abstände, Typografie und
Informationshierarchie blieben unverändert.**

Verifiziert: Tokens sind in `tailwind.config.js` definiert, im gebauten CSS
vorhanden (`.text-ink{color:rgb(30 41 59)}`) und in `Ideas.jsx` in Gebrauch.
**Technisch korrekt deployt** — die Seite sieht deshalb aus wie vorher.

→ Wer optische Verbesserung erwartet, braucht eine **eigene Design-Welle**
(Layout, Dichte, Hierarchie). Der Token-Sweep war deren *Vorarbeit*: Er macht
ein Redesign überhaupt erst zentral steuerbar.

---

## 7. Offen

| Punkt | Schwere |
|---|---|
| `mcp-server-v2` Restart-Schleife (`No module named 'mcp.server.fastmcp'`) | in Arbeit |
| Kein Runner auf dem Live-Server → Deploys bleiben manuell | Entscheidung offen |
| RLS auf Tabelle `tenants` selbst fehlt (Rest von 058 aktiv) | niedrig |
| `llm.py:247` — `json.loads()` auf LLM-Output (Gate G18) | niedrig |
| Kein automatisches Backup (kein Cron) | mittel |
| `/ideas` & Co. optisch schwach — Token-Sweep ≠ Redesign (Abschnitt 6) | Owner-Entscheid |
