# Migration Gitea → GitHub (2026-06-01)

Dieses Repo wurde von der internen Gitea-Instanz (`meister/content-autopilot-v2`)
nach GitHub (`inveloveritas123/content-autopilot-v2`, **privat**) migriert.
Die Git-Historie wurde dabei **umgeschrieben**, um exponierte Secrets zu entfernen.

## Was umgeschrieben wurde

Mit `git-filter-repo` über die **gesamte Historie** (alle 264 Commits, beide Branches):

| Entfernt / ersetzt | Vorher | Nachher |
|---|---|---|
| `.env.v2` (Datei) | echte Werte in 4 Commits | komplett aus Historie entfernt |
| Gitea API-Token | `9094…91e1` (in `CLAUDE.md`, `HANDOFF.md`, `scripts/`) | `***REMOVED-GITEA-TOKEN***`; Skripte lesen jetzt `GITEA_TOKEN` aus der Umgebung |
| Tenant-Key (alt, ZFB) | `cap-tenant-zfb-2026` | `***REMOVED-TENANT-KEY***` |
| Tenant-Key (aktuell, ZKG) | `cap-tenant-zkg-2026` | `***REMOVED-TENANT-KEY-ZKG***` |

Verifiziert mit `gitleaks` über `--log-opts="--all"`: keine echten Secrets mehr in
der Historie (verbleibende Treffer sind Platzhalter/Test-Werte, per `.gitleaks.toml`
allowlisted).

## ⚠️ Konsequenzen

- **Commit-Hashes haben sich geändert.** Die GitHub-Historie ist **nicht** mit der
  alten Gitea-Historie kompatibel — kein direkter `push`/`pull` zwischen beiden ohne
  Force-Sync. Lokale Alt-Clones neu klonen.
- **Alle betroffenen Secrets gelten als kompromittiert** (sie liegen weiterhin in der
  alten Gitea-Historie) und müssen **rotiert** werden:
  `DB_PASSWORD`, `REQUESTY_API_KEY`/`LITELLM_API_KEY`, `NEXTCLOUD_PASSWORD`,
  `MCP_CLIENT_SECRET`, `MCP_BEARER_TOKEN`, `DEFAULT_TENANT_KEY` sowie das
  **Gitea-Token** (in Gitea → Settings → Applications widerrufen) und der
  **aktuelle Tenant-Key** `cap-tenant-zkg-2026`.
- Der aktuelle Tenant-Key war zusätzlich im **Frontend-Bundle** hardcodiert
  (`frontend/src/main.jsx`) — nach Rotation serverseitig auflösen, nicht im Client.

## CI auf GitHub

`.gitea/workflows/*` laufen auf GitHub nicht. Ersatz unter `.github/workflows/`:

- **`secret-scan.yml`** — `gitleaks` bei jedem Push/PR + nightly (ersetzt das auf
  privaten Free-Repos nicht verfügbare GitHub Advanced Security Secret Scanning).
- **`tests.yml`** — hermetische Backend-Unit-Tests (315 grün). DB-gebundene
  Integrationstests (`tests/security`, `tests/test_telegram_webhook.py`) sowie
  12 vorbestehende Einzelfehler sind dort dokumentiert ausgenommen.

## Nicht möglich auf Free-Plan

Native Secret-Scanning/Push-Protection und Branch-Protection auf `main` erfordern
GitHub Pro für private Repos. Solange nicht aktiv: der `secret-scan`-Workflow dient
als Ersatz; `main` ist nicht PR-geschützt.
