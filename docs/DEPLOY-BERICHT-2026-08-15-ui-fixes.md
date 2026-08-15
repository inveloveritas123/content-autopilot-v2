# Deploy-Bericht — UI-Fixes auf LIVE (content-autopilot.zukunftsbund.de)

**Datum:** 2026-08-15 · Welle `zubu-deploy-ui-fixes`
**Auftrag:** Owner 2026-08-15, „dann bitte auf den 'live' server deployen per hand
wie gehabt die ganzen UI fixes"

---

## 1. Deployter Stand

- **SHA:** `82bd848fade00b0833ecf6a7bc542faf55d04259`
- **Branch:** `zubu-design-politur-work`
- **Basis:** `integration/highlander-2026-08-14` (`7fa68ce`)
- **Worktree-Quelle:** `_worktrees/zubu-design-politur` (working tree war clean,
  0 uncommittete Dateien — die im Briefing erwähnten uncommitteten Reste
  `Dialog.jsx`/`vite.config.js`/`CloseButton.jsx` waren zum Zeitpunkt des
  Deploys bereits in den Commits `6d07cd6`…`82bd848` aufgegangen)
- Übertragen via `git archive --format=tar.gz 82bd848` — nicht aus dem
  working tree, sondern exakt aus dem committeten Objekt, damit garantiert
  nichts Uncommittetes mitreist.
- 8 Commits, 17 Dateien, +531/−460 (Diff `7fa68ce..82bd848` gemessen,
  deckungsgleich mit Briefing-Angabe).
- **Keine Alembic-Migration im Diff** (`git diff --stat 7fa68ce..82bd848 --
  '*alembic*' '*migrations*'` → leer). Schritt 6 trotzdem gefahren, siehe 5.

## 2. Backup

```
/opt/backup/cap-v2-vor-ui-fixes-20260815-154015.dump                       (DB, 182K)
/opt/backup/code-vor-ui-fixes-20260815-154015.tar.gz                       (Code, 46M)
/opt/backup/env-vor-ui-fixes-20260815-154015                               (.env)
/opt/backup/docker-compose.override.yml-vor-ui-fixes-20260815-154015       (Domain-Anbindung)
```
Rückweg-DB: `sudo -u postgres pg_restore -d content_autopilot_v2 --clean --if-exists /opt/backup/cap-v2-vor-ui-fixes-20260815-154015.dump`

## 3. rsync `--dry-run --itemize-changes` — was wäre gelöscht worden

Einzige `*deleting`-Zeilen:
```
*deleting   backend/services/__pycache__/pipeline_llm.cpython-314.pyc
*deleting   backend/services/__pycache__/llm.cpython-314.pyc
*deleting   backend/services/__pycache__/
```
Nur Python-Bytecode-Cache, unschädlich (wird beim nächsten Backend-Start neu
erzeugt). Keine Löschung von `docker-compose.override.yml`, `.env` oder `/data`.
Nach dem echten Sync geprüft: beide Dateien unverändert vorhanden.

## 4. Asset-Hash — der Beweis

| | Datei |
|---|---|
| **vorher** | `assets/index-DWQvED_l.js` |
| **nachher** | `assets/index-CPSv3zBW.js` |

Hash hat sich geändert → Build ist angekommen.

## 5. Migration (Schritt 6)

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```
Keine `Running upgrade …`-Zeile — No-Op wie erwartet, DB bleibt bei Kopf `065`.

## 6. Verifikation gegen die Domain

```
curl -s -o /dev/null -w "%{http_code}\n" https://content-autopilot.zukunftsbund.de/
→ 200   (unmittelbar nach Neustart kurzzeitig 404, während nginx "health: starting"
   war — kein Falle-3.2-Vorfall, nach ~25s stabil 200, traefik-public-Netz war
   die ganze Zeit am Container gebunden)

curl -s https://content-autopilot.zukunftsbund.de/api/health
→ {"status":"ok","overall":"ok","version":"2.0.0",
   "checks":{"db":"ok","redis":"ok","storage_adapter":"degraded: unreachable"}}

curl -s https://content-autopilot.zukunftsbund.de/ | grep -o 'assets/[^"]*\.js'
→ assets/index-CPSv3zBW.js
```

⚠️ **Nebenbefund, nicht mein Scope:** `storage_adapter: degraded: unreachable`
im Health-Endpoint. Nicht untersucht (Auftrag war Deploy, kein Fix) — an Hub
gemeldet.

## 7. Visuelle Prüfung (Chrome DevTools MCP, gegen die Live-Domain)

1. **Dashboard:** „Heute — Samstag"-Box neutral weiß mit `border-surface-border`,
   Setup-Checkliste bleibt einzige mint-gradient Box. ✅ entkoppelt.
2. **/ideas:** „Manuelle Idee" öffnet Modal sauber (Overlay, Close-× oben rechts,
   Titel/Beschreibung/Angle/Hook-Felder). Modal schließt wieder. ✅
3. **/posts:** Toolbar zeigt EINE dunkelgrün gefüllte Primäraktion
   („Post erstellen"), Rest einheitlich sekundär/ghost (Serie erstellen,
   Triage-Modus, Focus-Triage, Leaderboard, CSV Export, Auto-Einplanen,
   Beste Zeiten, Hook-Bibliothek). Kein Farbchaos, Titel nicht gequetscht. ✅

Alle drei im Briefing genannten Prüfpunkte bestätigt.

## 8. Container-Status nach Deploy

```
content-autopilot-v2-nginx-v2-1:          healthy
content-autopilot-v2-backend-v2-1:        healthy
content-autopilot-v2-celery-worker-v2-1:  healthy
content-autopilot-v2-celery-beat-v2-1:    healthy
content-autopilot-v2-mcp-server-v2-1:     healthy (durchgehend seit 4h, unberührt)
content-autopilot-v2-redis-v2-1:          healthy (durchgehend seit 2 Tagen, unberührt)
```
`traefik-public`-Netz am nginx-Container bestätigt (Falle 3.2 vermieden,
beide `-f`-Flags verwendet).

## 9. Ergebnis

Deploy erfolgreich. Alle Prüfpunkte aus Briefing und Doku grün. Kein Code
geändert (Auftrag war reines Deployment). Ein Nebenbefund gemeldet
(`storage_adapter degraded`), nicht gefixt.
