# Abschlussbericht — Welle `zubu-deploy-bestand`, 15.08.2026

**Auftrag (Owner):** Bestand aufnehmen, dann Highlander deployen, DB fixen
wenn nötig. Interaktiv, im Dialog.

**Ergebnis:** Live-System steht und ist testbar. Der Login ist repariert, der
seit Tagen tote MCP-Server läuft, zwei stille Produktionsfehler sind behoben.

---

## 1. Was jetzt steht

### Live: https://content-autopilot.zukunftsbund.de

| Prüfung | Ergebnis |
|---|---|
| Domain | HTTP 200 |
| Health | `status: ok` · db ok · redis ok |
| Container | **7 von 7 healthy** (inkl. MCP) |
| Alembic | `065 (head)` — von 063 hochgezogen |
| Login-Kette | CSRF 200 → falsches Passwort 401 |
| Tenant-Auflösung | Liste **und** Rechteprüfung konsistent |
| LLM-Kette | echter Router-Call → HTTP 200 |
| Celery | alle Tasks laufen durch |

### Ausgeliefert
Highlander (62 Commits) + Auth-Fix (3) + PR #148 (WHERE-false) + 403-Teil aus
PR #147 + MCP-Pin + `user_tenant`-Seed (3 Zeilen).

### Highlander zusammengeführt
`integration/highlander-2026-08-14`: `5970f69` → **`5376144`**

Enthält nachweislich (`merge-base --is-ancestor` je Branch):
`deploy/live-20260815`, `zubu-deploy-bestand`, `zukunftsbund-user-login-defekt`,
`origin/fix/sqlalchemy-identitaetsvergleiche`.

**Entspricht bitgenau dem Live-Server** — md5 von `monitor_task.py`,
`pipeline_llm.py`, `llm.py`, `mcp-server/requirements.txt` identisch.
`main` bleibt echter Vorfahr → weiterhin fast-forward-fähig.

⛔ **Nicht gepusht** (Owner-Sache mit Robert, Hub bestätigt).

---

## 2. Die vier Befunde

### 2.1 Login: es fehlten Zuweisungen, kein Code-Bug
`users=3`, `agencies=1`, `tenants=1`, aber **`user_tenant=0`**. Robert und Ingo
hatten sich am 13.08. sogar erfolgreich eingeloggt — die Tenant-Liste blieb
trotzdem leer.

Vor dem Seed hätte die Liste den Tenant gezeigt und die Rechteprüfung ihn
verweigert (zwei verschiedene Auflösungswege). Nach dem Seed: beide konsistent,
alle drei sehen ihren Tenant.

### 2.2 21× `WHERE false` — stiller Totalausfall
`Source.is_active is True` ist ein Python-Identitätsvergleich, ergibt immer
`False`, SQLAlchemy kompiliert zu `WHERE false`.

Bewiesen im Prod-Container:
```
kaputt : SELECT s.id FROM s WHERE false
korrekt: SELECT s.id FROM s WHERE s.is_active IS true
```
Betroffen u. a. `monitor_all_sources()` — läuft im Minutentakt und fand **nie
eine Quelle**. In den Logs von Normalbetrieb nicht unterscheidbar.

Fix lag seit 04.08. als PR #148 offen. **Im Deploy enthalten**; über den
weiteren Umgang (PR mergen) entscheidet der Owner.

### 2.3 MCP-Server: offene Versionsobergrenze
`mcp>=1.0.0` ohne Obergrenze → pip zog 2.0.0 → `mcp.server.fastmcp` entfernt →
Restart-Schleife seit 13.08., tagelang unbemerkt (die anderen sechs Container
meldeten „healthy").

Pin auf `<2.0.0`, Kompatibilität von 1.29.0 vorher im Wegwerf-Container
geprüft. **Läuft: RestartCount 0, HTTP 200 auf `/sse`.**

Bewusst **nicht** auf die 2.x-API portiert — 12 Aufrufstellen, eigener Vorgang.

### 2.4 403 löste den Env-Fallback nicht aus
Selbstheilungspfad behandelte nur `401`. Der Router antwortet bei einem
veralteten DB-Key aber mit `403` → Fallback lief nie an → Post-Generierung
brach ab, während Transkription weiter Erfolg meldete.

Nur diesen Teil aus PR #147 übernommen; dessen zweiter Teil (P08-Stub) ist im
Highlander bereits besser gelöst.

---

## 3. Zwei Fehler von mir — und was sie gekostet haben

### 3.1 Zwei Stunden auf dem falschen Server
Ich habe `152.53.142.163` vermessen und als „Prod" berichtet. Das Live-System
ist `128.140.67.21`.

**Ursache:** Ich habe den Registry-*Projekteintrag* gelesen (nennt die alte IP
und zwei Domains, die im DNS nicht mehr auflösen) und danach selbst
weitergesucht, statt in `hosts.json` und den Runbooks nachzusehen. Die richtige
Adresse stand in `ZUKUNFTSBUND_SERVER_HAERTUNG_VOLLZUG.md` Zeile 4 — mit
demselben SSH-Key, den ich schon hatte.

**Folge, wäre es unbemerkt geblieben:** Die Owner-Freigabe („DB droppen wenn
nötig") hätte 2.765 fremde Posts des Tenants ZKG getroffen, und der Deploy wäre
auf der falschen Kiste gelandet.

**Regel daraus:** Registry-SSOT vor Eigenrecherche. Ein veralteter Eintrag ist
kein Grund, selbst zu suchen — sondern einer, die anderen Quellen zu lesen.

### 3.2 Eine Fehlmessung als Bug gemeldet
Ich meldete „Tenant erscheint dreifach". Das war ein Fehler **meiner
Prüf-Query** (JOIN über `user_tenant` × `agency_id` multipliziert), nicht der
Anwendung. Der Produktivcode nutzt für `owner` einen anderen Weg und liefert
korrekt genau einen Treffer.

**Regel daraus:** Eine nachgebaute Query beweist nichts — es zählt die, die der
Code wirklich absetzt.

---

## 4. Zwei Fallen im Deploy-Weg (dokumentiert in DEPLOY-WEG-UND-ZUSTAND.md)

**`rsync --delete` hätte die Domain-Anbindung gelöscht.**
`docker-compose.override.yml` liegt nur auf dem Server, nicht im Repo, und
enthält die Traefik-Labels. Vom Trockenlauf abgefangen — deshalb gehört vor
jeden rsync ein `--dry-run`.

**Ein einzelnes `-f` schaltet die Override-Datei ab.**
Symptom: HTTP 404 auf der Domain, während alle Container „healthy" melden.
Ist eingetreten, Seite war ca. eine Minute offline. Fix: immer beide `-f`.

---

## 5. Offen — wartet auf Entscheidung

| # | Punkt | Wer entscheidet |
|---|---|---|
| 1 | **Highlander pushen?** Steht lokal auf `5376144` | Owner + Robert |
| 2 | **PR #148 mergen?** Hub-Empfehlung liegt beim Owner | Owner |
| 3 | **Neues Repo?** Nur `content-autopilot-v2` sichtbar | Robert |
| 4 | **Runner auf dem Live-Server?** Sonst bleiben Deploys manuell | Owner |
| 5 | **Design-Welle für `/ideas` & Co.?** Token-Sweep war kein Redesign | Owner |

## 6. Offen — technisch, nicht blockierend

| Punkt | Schwere |
|---|---|
| RLS auf Tabelle `tenants` selbst fehlt (43 Tabellen aktiv) | niedrig |
| Kein Backup-Cron auf dem Live-Server | mittel |
| 8 ungepinnte Pakete in `backend/requirements.txt` (gemeldet) | latent |
| `llm.py:247` — `json.loads()` auf LLM-Output (Gate G18) | niedrig |
| Zum Durchspielen fehlen Bot, Quellen, Voice-/Firmenprofil | Einrichtung |

---

## 7. Rückwege

```
/opt/backup/cap-v2-vor-highlander-20260815-112337.dump      (DB)
/opt/backup/code-vor-highlander-20260815-112337.tar.gz      (Code)
/opt/backup/env-vor-highlander-20260815-112337              (.env)
/opt/backup/docker-compose.override.yml-20260815-112337     (Domain-Anbindung)

backup/highlander-vor-integration-20260815 → 5970f69
deploy/live-20260815                       → 599a9fc
```

⚠️ Ein Code-Rollback allein reicht nicht — Migrationen `064`/`065` bleiben
angewandt (beide additiv, per `alembic downgrade` revertierbar).

---

## 8. Werkzeug-Befund

`lc_integrate_batch.sh` ist fest auf `main` verdrahtet — kein Ziel-Argument,
und `main` steckt auch in den Bilanz-Rechnungen. Für ein anderes Integrationsziel
unbrauchbar.

Vom Hub bestätigt und als `orko-integrate-batch-nur-gegen-main` (P2) eingetragen;
der Hub lief am selben Tag in dieselbe Wand. Ich habe deshalb von Hand
integriert (`ORKO_MANUAL_GIT_OK=1`, eigener Worktree, Trockentest vorab,
Rückweg gesichert) und das Werkzeug **nicht** angefasst.
