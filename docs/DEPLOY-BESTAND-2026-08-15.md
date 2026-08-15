# Deploy-Bestand Content Autopilot v2 — 15.08.2026

**Erhoben:** 2026-08-15, 12:00–12:30 CEST · Welle `zubu-deploy-bestand`
**Modus:** reine Messung, nichts geändert, nichts gepusht.

Jede Zahl trägt ihre Herkunft: **[gemessen]** mit Kommando · **[Datei]** mit Pfad ·
**[NICHT MESSBAR]**.

---

## 0. Kurzfassung für Eilige

| Frage | Antwort |
|---|---|
| Kommen wir auf den Server? | **Ja** — aber als User `ingo`, nicht `meister` |
| Gibt es eine Deploy-Kette? | **Ja, vollautomatisch via GitHub Actions** — nur an `main` gebunden |
| Kann der Highlander über GitHub deployt werden? | **Ja**, mit einer Änderung an 2 Zeilen |
| Ist die DB in Ordnung? | **Nein** — zwei Migrationen sind als angewandt markiert, aber real nicht vorhanden |
| Läuft die App? | **Ja**, seit 46 h stabil — außer MCP-Server (Dauer-Crash) |
| Behebt der Auth-Fix den Login? | **Nein, nicht allein** — es gibt null Benutzer in der DB |

**Die zwei Dinge, die vor einem Deploy geklärt sein müssen:**
1. Schema-Drift 057/058 (RLS fehlt real → Mandantentrennung nicht aktiv)
2. Es existiert kein einziger Benutzer — der Login-Fix läuft ins Leere

---

## 1. Ist-Stand

### 1.1 Zugang

**Korrektur der bisherigen Annahme:** SSH war nie blockiert, es wurde der
falsche Benutzer getestet.

| Variante | Ergebnis |
|---|---|
| `ingo@` + Key `zukunftsbund-ops` | **funktioniert** |
| `meister@` (beide Keys) | Permission denied |
| `root@` | Permission denied |
| Port 22 | Connection refused (nur 10022) |

[gemessen] `ssh -i ~/.ssh/zukunftsbund-ops -p 10022 ingo@152.53.142.163`

Der Benutzer `ingo` ist in den Gruppen `sudo` und `incus-admin`, `sudo -n` ist
passwortlos. Damit ist alles Nötige erreichbar.

⚠️ **Der Registry-Eintrag `registry/projects/zukunftsbund_content_autopilot.json`
nennt `meister` — das ist falsch und sollte korrigiert werden.**

### 1.2 Server-Topologie

Der Code läuft **nicht** direkt auf dem Hetzner-Host, sondern in einem
Incus-Container. Das ist der häufigste Stolperstein: auf dem Host gibt es
`/opt/content-autopilot-v2` nicht.

```
Hetzner-Host (v2202603322602440403, up 80 Tage)
└── Incus-Container "content-autopilot"   ← PRODUKTIV, 10.30.0.136
    └── Docker: 8 Container in /opt/content-autopilot-v2
└── Incus-Container "content-autopilot-testcontainer"  ← 10.30.0.219
    └── Docker: 6 Container (Stand vom 14.08.)
```

[gemessen] `incus list`

### 1.3 Dienste (Produktiv-Container)

| Container | Status |
|---|---|
| nginx-v2 | Up 46 h (healthy), Port 8601 + 8611 |
| backend-v2 | Up 46 h (healthy) |
| celery-worker-v2 | Up 46 h (healthy) |
| celery-beat-v2 | Up 46 h (healthy) |
| redis-v2 | Up 46 h (healthy) |
| nextcloud-web/app | Up 2 Monate (healthy) |
| **mcp-server-v2** | **Restarting — Dauer-Crash** |

[gemessen] `docker ps`

**Backend-Health** [gemessen, direkt gegen `localhost:8000/api/health`]:
```json
{"status":"ok","version":"2.0.0",
 "checks":{"db":"ok","redis":"ok","storage_adapter":"degraded: unreachable"}}
```

**Telegram-Bot läuft** — Beat sendet alle 5 s `telegram-poll-active-bots`,
dazu `monitor-sources-check-due` und `publish-scheduled-posts`.
[gemessen] `docker logs celery-beat-v2`

**MCP-Server ist seit mindestens 46 h kaputt** [gemessen] `docker logs mcp-server-v2`:
```
ModuleNotFoundError: No module named 'mcp.server.fastmcp'
```
Ein Abhängigkeitsproblem im Image, kein Konfigurationsfehler.
Betrifft `mcpcontent.zukunftsbund.de`. **Besteht unabhängig vom Deploy und wird
durch ihn nicht behoben** — das MCP-Image wird vom Deploy-Workflow gar nicht
neu gebaut.

### 1.4 Code-Stand auf dem Server

**Der Server ist kein Git-Checkout.** [gemessen] — `git -C /opt/content-autopilot-v2`
meldet `not a git repository`. Der Code kommt per `rsync --delete` vom
GitHub-Runner (siehe 2.1).

Letzter Deploy: **13.08.2026, 11:58** (Dateizeitstempel), passend zur
Backup-Datei `..._vor_stufe2_deploy_2026-08-13.dump`.

Migrationsdateien auf dem Server: bis `063`, **keine 064/065**. [gemessen]

### 1.5 Datenbank

DB `content_autopilot_v2`, User `autopilot`. Alembic: `063 (head)` — Code und
`alembic_version` stimmen überein. [gemessen] `alembic current`

**Belegung der Auth-Tabellen** [gemessen]:

| Tabelle | Zeilen |
|---|---|
| tenants | **11** |
| users | **0** |
| user_tenant | **0** |
| agencies | **0** |

Die 11 Tenants sind überwiegend Testdaten (`E2E Canonical` ×4, `Test: …`,
`S2 Fallback Test`). Fachlich relevant wirken nur **Louis MVP**,
**Eric Spielhaus**, **ZKG**.

---

## 2. Deploy-Kette — die Antwort auf „geht das über GitHub?"

### 2.1 Es gibt sie bereits, und sie ist vollständig

**Ja, das geht — der Weg existiert schon und ist gebaut.**
[Datei] `.github/workflows/deploy.yml`, `docs/DEPLOY.md`

```
Push auf main
  → Workflow "Tests (pytest)" läuft
  → Gate-Job (GitHub-hosted) prüft: Tests UND Lint grün für DIESE SHA?
  → Deploy-Job auf SELF-HOSTED Runner im Incus-Container:
       1. rsync -a --delete  (ohne .git, .env, node_modules, /data)
       2. npm ci && npm run build   (Frontend auf Host — nicht in Docker)
       3. docker compose build backend/celery-worker/celery-beat/nginx
       4. alembic upgrade head
       5. up -d --force-recreate + restart nginx + Health-Check (30×5 s)
```

**Der Runner läuft** [gemessen]:
`actions.runner.inveloveritas123-content-autopilot-v2.kolonie-incus.service`
— `active running`, Prozess seit 28.07.

Kein SSH, keine Deploy-Secrets nötig: Der Runner sitzt im Zielcontainer und hat
direkten Dateisystem- und Docker-Zugriff.

### 2.2 Was fehlt für den Highlander

Der Trigger ist **hart auf `main` verdrahtet** — an genau **zwei funktionalen
Stellen** [gemessen] `grep -n main .github/workflows/deploy.yml`:

```yaml
Zeile 27:    branches: [main]
Zeile 57:    github.event.workflow_run.head_branch == 'main'
```
(Zeile 3 ist nur ein Kommentar. Der Gate-Job prüft zusätzlich die SHA.)

Es gibt bereits `workflow_dispatch: {}` — **ein manueller Start ist also schon
heute vorgesehen.**

#### ⚠️ Nachtrag 15.08. (nach Owner-Entscheid, Abschnitt 2.2 korrigiert)

**Für Weg A sind vermutlich GAR KEINE Workflow-Änderungen nötig.** Die oben
genannten zwei Zeilen betreffen ausschließlich den *automatischen* Trigger.
Beim manuellen Start über `workflow_dispatch` mit Branch-Auswahl greift eine
andere Kette [gemessen, `.github/workflows/deploy.yml` Zeilen 53–107]:

1. Die `if`-Bedingung des Gate-Jobs ist über den ersten Zweig bereits erfüllt:
   `github.event_name == 'workflow_dispatch' || (…head_branch == 'main')`
   → der `main`-Teil wird bei manuellem Start gar nicht ausgewertet.
2. `SHA` fällt zurück auf `github.sha` = **HEAD des gewählten Branches**
   (`${{ github.event.workflow_run.head_sha || github.sha }}`).
3. Der Gate sucht Tests/Lint **allein über `head_sha`**, ohne Branch-Bezug:
   `runs?head_sha=${SHA}&status=completed`
4. Der Deploy-Job checkt exakt diese SHA aus (`ref: needs.gate.outputs.sha`).

**Voraussetzung, die erfüllt ist** [gemessen]: Beide Pflicht-Workflows laufen
auf `push: branches: ["**"]` — also auch auf dem Highlander-Branch. Der Gate
findet ihre Ergebnisse.

→ **Praktisch heißt das:** Highlander pushen, warten bis Tests + Lint für dessen
HEAD-SHA grün sind, dann „Deploy (Server B)" manuell mit Branch
`integration/highlander-2026-08-14` starten. Kein Workflow-Patch, keine
Änderung an einer Datei, die auf `main` zurückgemergt werden müsste.

⚠️ **Noch nicht verifiziert:** ob die GitHub-Oberfläche den Branch zur Auswahl
anbietet — `workflow_dispatch` listet nur Branches, in denen die Workflow-Datei
**bereits existiert**. Da `deploy.yml` aus `main` stammt und der Highlander ein
Fast-Forward darauf ist, ist die Datei dort vorhanden. **[NICHT MESSBAR]** ohne
Push.

### 2.3 Bewertung des Owner-Vorschlags

> *„highlander branch auf GitHub anlegen und von dort deployen"*

Das ist der richtige Weg, und er ist billiger als gedacht:

**Voraussetzung, die bereits erfüllt ist:** `main` und der Highlander sind
**nicht divergent**. [gemessen]
```
Highlander vor main: 62 Commits
main vor Highlander:  0 Commits
Merge-Base = aaefc30 = aktueller main-HEAD
```
Der Highlander ist ein **sauberer Fast-Forward auf `main`**. Die im Hub-Briefing
genannte „bekannte Divergenz mit 109 main-Commits" trifft **nicht mehr zu** —
`main` ist vollständig im Highlander enthalten.

### 2.4 Die Migrations-Umbenennung — und warum sie kein Problem ist

[gemessen] `git diff --name-status main..integration/highlander-2026-08-14`:

```
R076  057_setup_pipeline_run_stage_p12.py      → 064_setup_pipeline_run_stage_p12.py
R071  058_source_item_transcription_attempts.py → 065_source_item_transcription_attempts.py
A     057_tenant_agentur_id.py  058_rls_tenant_isolation.py  059…063
```

**Was passiert ist:** Auf `main` waren `057`/`058` mit *anderen* Migrationen
belegt. Der Highlander bringt eigene `057`–`063` mit; die beiden `main`-Migrationen
wurden deshalb nach hinten auf `064`/`065` umnummeriert.

**Bewertung: sauber gelöst.** Die Revisionskette im Highlander ist
lückenlos linear `049→050→053→…→063→064→065`, **genau ein Head**. [gemessen]

**Entscheidend für den Deploy:** Die Prod-DB steht auf `063`, und die `063` auf
dem Server ist **dieselbe** wie im Highlander (`down_revision=062`, identische
Kette bis 050 verifiziert). Es gibt **keinen Nummernkonflikt** — `alembic
upgrade head` würde sauber `064` und `065` nachziehen.

⚠️ Das gilt nur, solange nichts von `main` mit den alten `057`/`058` je auf diese
DB gelaufen ist. Verifiziert: Der Server hat die alten Dateien nicht, und
`alembic_version` enthält genau eine Zeile (`063`). [gemessen]

---

## 3. ⚠️ Der schwerwiegendste Befund: Schema-Drift

**Alembic behauptet `063` angewandt. Zwei dieser Migrationen sind real nicht
vorhanden.**

[gemessen] Prüfung jeder Migration gegen das reale Schema:

| Migration | Alembic sagt | Realität |
|---|---|---|
| 057 `tenants.agentur_id` | angewandt | **Spalte fehlt** |
| 058 RLS Mandantentrennung | angewandt | **fehlt** |
| 059 users / user_tenant | angewandt | vorhanden |
| 060 memory_chunks tsvector | angewandt | vorhanden |
| 061 llm_trace | angewandt | vorhanden |
| 063 ai_generated | angewandt | vorhanden |

Belegt zusätzlich dadurch, dass ein `SELECT agentur_id FROM tenants` mit
`UndefinedColumnError: column "agentur_id" does not exist` scheitert. [gemessen]

### 3.1 RLS ist nicht aktiv — Mandantentrennung existiert nicht

Migration 058 soll RLS auf **41 Tenant-Tabellen** setzen
[Datei] `backend/alembic/versions/058_rls_tenant_isolation.py`.

Real aktiv [gemessen, `pg_class` / `pg_policies`]:
```
TABELLEN MIT RLS AKTIV: 2   → llm_trace, tenant_concurrency
RLS-POLICIES gesamt:    2
```
Die beiden aktiven stammen aus 061/062, die ihre Policy selbst mitbringen.
**Von 058 ist nichts angekommen.**

**Schadensszenario:** Die datenbankseitige Mandantentrennung, die laut
Migration ausdrücklich „fail-closed" sein soll, ist nicht vorhanden. Die
Isolation hängt allein daran, dass der Anwendungscode überall korrekt filtert.
Ein vergessener Filter liefert fremde Mandantendaten aus, ohne dass die DB
eingreift. Bei einem Mehrmandanten-System mit Kundendaten ist das
DSGVO-relevant (Art. 32 — Sicherheit der Verarbeitung).

**Warum es niemandem auffiel:** Es gibt nur Testkunden und der Code filtert
offenbar korrekt; RLS ist die *zweite* Verteidigungslinie, deren Fehlen im
Normalbetrieb unsichtbar bleibt.

### 3.2 Wie konnte das passieren?

Nicht abschließend geklärt. **[NICHT MESSBAR]** ohne Deploy-Historie.
Plausibelste Erklärung: Bei einem früheren Deploy wurde `alembic stamp` statt
`upgrade` benutzt, oder eine Migration lief teilweise und die Version wurde
trotzdem hochgesetzt. Der Sprung in der Nummerierung (050 → 053, es gibt kein
051/052) deutet auf frühere manuelle Eingriffe.

### 3.3 Gute Nachricht: der Reparatur-Cast ist sicher

Migration 058 castet `tenant_id` auf 14 Tabellen von Text auf UUID — mit der
im Kopf dokumentierten Annahme *„greenfield, keine Altdaten"*.

**Diese Annahme ist falsch:** Es liegen 394 Zeilen in diesen Tabellen.
**Der Cast wäre trotzdem sicher** [gemessen]: In allen 14 Tabellen sind
**0 Werte ungültige UUIDs**.

| Tabelle | Typ | Zeilen | ungültige UUID |
|---|---|---|---|
| daily_cost_tenant | text | 145 | 0 |
| setup_pipeline_run | text | 83 | 0 |
| telegram_message_log | text | 76 | 0 |
| bot_session | text | 35 | 0 |
| wizard_session | text | 28 | 0 |
| tenant_customer_context | text | 8 | 0 |
| tenant_voice_profile | text | 6 | 0 |
| tenant_audience_avatar | text | 6 | 0 |
| tenant_telegram_link | text | 3 | 0 |
| tenant_bot_config | text | 3 | 0 |
| tenant_customer_values | text | 1 | 0 |
| backtest_runs, tenant_review_queue, voice_drift_observation | – | 0 | – |

Ein Nachziehen von 057/058 ist also technisch machbar — **aber es ist ein
Schema-Eingriff und braucht Owner-Freigabe.**

---

## 4. Der Login-Fix und warum er allein nicht reicht

Der Branch `zukunftsbund-user-login-defekt` sitzt sauber **3 Commits auf dem
Highlander** auf (0 zurück), berührt 3 Dateien [gemessen]:
```
backend/api/auth.py                    19 +-
backend/services/auth.py               13 +-
backend/tests/test_auth_user_login.py 193 +++   (neu)
```

**Der Fix ist inhaltlich richtig und passt zur Server-Realität.** Er ersetzt den
Join über `tenants.agentur_id` durch echte Fremdschlüssel
(`user_tenant` → `users.agency_id`). Beide Tabellen existieren auf Prod mit
genau diesen Spalten [gemessen] — der Fix läuft dort also, **und er umgeht
zugleich die fehlende Spalte `agentur_id` aus 3.1.**

**Aber:** Er behebt den Login trotzdem nicht, denn
```
users = 0 · user_tenant = 0 · agencies = 0
```
Der Vorgänger-Storko hat genau das vorhergesagt. Es ist bestätigt:
**Ohne Benutzer bleibt die Tenant-Liste zu Recht leer.** Es fehlt ein Seed,
kein Code.

⚠️ **Konsequenz:** Wer nach dem Deploy den Login testet und „geht immer noch
nicht" meldet, hat recht — aber aus einem anderen Grund. Der Erfolg des Deploys
darf nicht am Login gemessen werden, solange kein Benutzer angelegt ist.

**Offene Frage an den Owner:** Wer soll Zugang bekommen (Robert? Louis? Eric?)
und mit welcher Rolle/Agentur? Das ist eine fachliche Entscheidung, keine
technische. Es gibt `scripts/ci-bootstrap-tenant.sh` und `ci-seed-tenant.sql`
[Datei] — ob die für echte Benutzer taugen, ist ungeprüft.

---

## 5. Was der Highlander fachlich bringt

62 Commits. Nicht einzeln geprüft — **[NICHT MESSBAR]** in der verfügbaren Zeit.
Aus den Migrationen 057–065 ableitbar:

- **058** RLS-Mandantentrennung (die real fehlt, s. 3.1)
- **059** Benutzer-Authentifizierung (users/user_tenant) — Grundlage des Kunden-Logins
- **060** Volltextsuche auf memory_chunks
- **061** LLM-Trace (Kostenverfolgung)
- **062** Tenant-Nebenläufigkeit
- **063** KI-Kennzeichnung (`ai_generated`) — vermutlich EU-AI-Act-relevant
- **064/065** Pipeline-Stufen, Transkriptions-Wiederholungen
- zuletzt: DSGVO-Fix (gelöschte memory_chunks tauchten in der Suche auf)

⚠️ **059–063 sind laut `alembic_version` bereits auf Prod** — der Highlander
bringt an DB-Änderungen also im Wesentlichen nur noch **064/065** plus die
**Reparatur des Drifts** aus 3.1.

---

## 6. Risiken des geplanten Deploys

| # | Risiko | Schwere | Bewertung |
|---|---|---|---|
| R1 | RLS fehlt real (3.1) | **hoch** | Besteht schon jetzt. Deploy behebt es nicht automatisch. |
| R2 | Kein Benutzer in der DB (4.) | **hoch** | Login bleibt defekt, Deploy wirkt „gescheitert" |
| R3 | `rsync --delete` löscht Server-Dateien | mittel | `.env` und `/data` sind ausgenommen [Datei] — geprüft |
| R4 | 62 Commits ungetestet auf Prod | mittel | CI-Gate erzwingt grüne Tests, aber kein Staging-Durchlauf |
| R5 | MCP-Server bleibt kaputt | niedrig | Wird vom Deploy nicht angefasst |
| R6 | Frontend-Build schlägt fehl | niedrig | Läuft auf Host, in der Kette etabliert |
| R7 | Kein externes Backup | mittel | Backups liegen nur lokal in `/opt/backup` |

### Backup-Lage [gemessen] `ls -laht /opt/backup/`

```
11M  13. Aug 11:57  content_autopilot_v2_vor_stufe2_deploy_2026-08-13.dump
9.8M  4. Aug 11:49  cap-v2-pre-migration-20260804-1345.sql.gz
```

⚠️ **Das dokumentierte tägliche Backup läuft nicht.** `scripts/daily_backup.sh`
existiert und ist für `0 3 * * *` vorgesehen [Datei], aber **es gibt keinen
Cron-Eintrag** — `crontab -l` ist leer, `/etc/cron.d/` enthält nur
`e2scrub_all` und `sysstat`. [gemessen]

Das jüngste Backup ist **2 Tage alt** und stammt aus dem letzten Deploy, nicht
aus einer Automatik. Beide Backups liegen **nur lokal auf derselben Maschine**.

⚠️ Der Produktiv-Container hat 2 Incus-Snapshots, beide **veraltet**
(02.06. und 11.06.). Der Testcontainer hat **keine**. [gemessen] `incus info`

---

## 7. Empfehlung

### 7.1 Reihenfolge

**Schritt 0 — vor allem anderen: Backup.**
```
incus snapshot create content-autopilot vor-highlander-20260815
```
Dazu ein frischer `pg_dump` nach `/opt/backup/`. Der Snapshot ist der
verlässlichste Rückweg, weil er Code *und* DB in einem Zug erfasst.
**Kosten: Minuten. Ohne ihn kein Deploy.**

**Schritt 1 — Highlander auf GitHub bringen.**
Da `main` ein echter Vorfahr ist (2.3), gibt es zwei Wege — **Owner-Entscheidung**:

| | A) Highlander als Branch pushen | B) Fast-Forward auf `main` |
|---|---|---|
| Vorgehen | `integration/highlander-2026-08-14` pushen, Workflow um diesen Branch erweitern | Highlander nach `main` mergen (FF) |
| Deploy | manuell via `workflow_dispatch` | läuft automatisch |
| Workflow-Änderung | ja (2 Zeilen) | **keine** |
| Owner-Regel „main nicht pushen" | eingehalten | **verletzt** |
| Rückweg | `main` bleibt unberührt | nur über Revert |

→ **Empfehlung A**, weil es der Owner-Regel entspricht und `main` als
Rückfallebene intakt lässt. B wäre technisch der kürzere Weg (kein
Merge-Konflikt möglich, da FF), gibt aber die Rückfallebene auf.

**Schritt 2 — Auth-Fix einbeziehen.**
Die 3 Commits vor dem Deploy in den Highlander mergen (konfliktfrei, da direkt
darauf aufgebaut). Sonst deployen wir wissentlich einen kaputten Login.

**Schritt 3 — Deploy auslösen**, Kette wie 2.1. Prüfpunkte:
- Gate grün (Tests + Lint auf derselben SHA)
- `alembic current` = `065`
- `/api/health` → `status: ok`
- Celery-Beat pollt weiter

**Schritt 4 — Schema-Drift reparieren.** ⚠️ **Getrennt vom Deploy, mit eigener
Freigabe.** Nicht im selben Zug, damit bei einem Fehler klar ist, woran es lag.

**Schritt 5 — Benutzer anlegen** (fachliche Klärung nötig, s. 4.).

### 7.2 Rückweg

| Was schiefgeht | Rückweg |
|---|---|
| Health-Check rot nach Deploy | Incus-Snapshot zurückspielen (Code + DB in einem) |
| Nur Migration schlägt fehl | `alembic downgrade -1`; 064/065 sind additiv → revertierbar |
| Frontend kaputt, Backend ok | nur nginx aus altem Image neu bauen |
| Alles unklar | Snapshot `vor-highlander-20260815` — deshalb Schritt 0 |

`scripts/safe_alembic.sh` macht Snapshot, Health-Check und **Auto-Rollback bei
rotem Health** [Datei] — die Migration sollte darüber laufen, nicht über
nacktes `alembic upgrade`. ⚠️ Der Deploy-Workflow ruft aktuell **nacktes
`alembic upgrade head`** auf, nicht `safe_alembic.sh` [Datei]
`.github/workflows/deploy.yml`. Das ist eine Lücke.

---

## 8. Was ich nicht weiß

- **Was die 62 Commits fachlich ändern** — nur aus Migrationen abgeleitet (5.)
- **Wie der Drift entstand** (3.2) — keine Deploy-Historie greifbar
- **Ob der Testcontainer aktuell ist / wofür er dient** — nicht untersucht
- **Ob `ci-seed-tenant.sql` für echte Benutzer taugt** — nicht gelesen
- **Ob Traefik/TLS und die Domains sauber stehen** — nur intern gemessen,
  nicht von außen gegen `cap.zukunftsbund.de`
- **Ob v1 (Pitch Alpha) noch läuft** — bewusst nicht angefasst

---

## 9. Entscheidungen

### 9.1 Getroffen — Owner, 15.08.2026

**1. Weg A** (aus 7.1): Highlander als eigener Branch nach `origin`,
Deploy-Start manuell via `workflow_dispatch`. `main` wird **nicht** gepusht und
bleibt Rückfallebene. Weg B (Fast-Forward auf `main`) wurde ausdrücklich
verworfen, obwohl technisch konfliktfrei möglich — die Rückfallebene wiegt
schwerer als die Ersparnis.

**2. Auth-Fix wird mitdeployt**: `zukunftsbund-user-login-defekt` (3 Commits)
kommt vor dem Deploy in den Highlander.

**Trockentest dazu** [gemessen]: `git merge-tree` gegen die Merge-Base zeigt
**keine Konfliktmarker**; die Merge-Base *ist* der Highlander-HEAD, der Merge
ist also ein sauberer Fast-Forward. Risikolos.

### 9.2 Offen — bewusst nach dem Deploy

3. **Schema-Drift 057/058 reparieren** — wann, mit welcher Freigabe?
   (Getrennt vom Deploy, damit Fehler zuordenbar bleiben.)
4. **Wer bekommt einen Benutzer?** (Robert / Louis / Eric, Rolle, Agentur)
   — fachliche Entscheidung, blockiert den Deploy nicht, aber ohne sie ist der
   Login nicht testbar (s. 4.).
5. **Tägliches Backup aktivieren?** Cron fehlt (6.) — eine Zeile.
6. **MCP-Server reparieren?** Eigener Vorgang, unabhängig vom Deploy.

### 9.3 Noch ausstehend: die Push-Freigabe selbst

Die Wegentscheidung ist getroffen, die **Ansage zum Push aber noch nicht
erteilt**. Bis dahin gilt Phase 1: gemessen und vorbereitet wird, gepusht
nicht.

---

## Anhang: Nebenbefund zur Infrastruktur

Der Arbeits-Worktree dieser Welle ist während des Laufs **zweimal von außen
verschwunden** (12:0x und erneut gegen 12:4x). Beim zweiten Mal ging dieser
Report verloren, weil er uncommittet war; der Inhalt lag im Sitzungsverlauf vor
und wurde daraus rekonstruiert. Kein Verlust an Messdaten.

Der Hub führt das als bekannten Defekt
(`orko-worktree-verschwindet-auch-im-laufenden-betrieb`, P1, heute fünfmal
aufgetreten, Ursache unbelegt). Konsequenz für diese Welle: nach jedem
Arbeitsschritt wird committet.
