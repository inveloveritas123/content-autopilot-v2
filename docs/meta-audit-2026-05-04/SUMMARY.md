# META-AUDIT — SUMMARY (2026-05-04)

**Issue:** #153 — Tiefen-Code-Audit gegen echten Source-Code  
**Repo-Stand:** main @ 76b8ae2 (lokal /home/meister/content-autopilot-v2)  
**Methode:** 4 parallele Explorer-Subagents (Haiku) auf 9 Bereiche A-I gegen `find/grep/cat`. Keine Plan-Dokumente gelesen.  
**Phase-1-Surface-Diff:** NICHT MÖGLICH — `META-Phase1-Surface-Analyse-2026-05-04.md` aus dem Cowork-Workspace nicht verfügbar. Audit ist also reiner Real-Status, kein Vergleich.

---

## Pro-Bereich-Status

| Bereich | Status | Datei | Kern-Aussage |
|---|---|---|---|
| **A — Modularität** | ❌ | `A_modularity.md` | Bot + Storage hardcoded; LLM-Provider 🟡 teilweise modular |
| **B — YouTube** | 🟡 | `B_youtube.md` | YouTube-Suche + Transkriptions-Task vorhanden, aber keine `transcripts`-Tabelle |
| **C — Security** | 🟡 | `C_security.md` | CSRF + Injection-Schutz ✅; aber Frontend-Hardcoded-Key + alle Container als root |
| **D — Doku** | 🟡 | `D_documentation.md` | 7 READMEs + strukturiertes Logging ✅; 0 OpenAPI, 0 ADRs |
| **E — Portabilität** | 🟡 | `E_portability.md` | `.env.example` + `setup.sh` ✅; aber 10 hardcoded Pfade, davon 1× v1-Path |
| **F — DSGVO** | ❌ | `F_dsgvo.md` | `llm_call_logs` ✅; aber kein Consent (#73), kein Right-to-Deletion (#106), kein Export |
| **G — Usability** | ✅ | `G_usability.md` | 50 JSX-Pages, 14 Routes, 50 Responsive-Patterns, WCAG-Touch-Targets |
| **H — SOTA/Skalierung** | ✅ | `H_sota_scale.md` | Stack aktuell (FastAPI 0.115, React 18.3, SQLAlchemy 2.0); Sentry full-stack ✅; Prometheus ❌ |
| **I — Tech-Debt** | 🟡 | `I_techdebt.md` | Nur 6 TODOs ✅; aber `Posts.jsx` 3460 Zeilen 🔴 |

---

## Konsolidierte Top-10 Findings

| # | Bereich | Severity | Finding | Quelle | Aufwand |
|---|---|---|---|---|---|
| 1 | C-Security | 🔴 CRITICAL | Hardcoded Tenant-Key `***REMOVED-TENANT-KEY-ZKG***` im Frontend-Bundle | `frontend/src/main.jsx:9` | S |
| 2 | C-Security | 🟡 HIGH | Alle Container laufen als root (kein `USER`-Direktive in Dockerfiles) | `*/Dockerfile` × 5 | S |
| 3 | I-TechDebt | 🟡 HIGH | `Posts.jsx` mit 3460 Zeilen — SRP verletzt, Bundle-Performance-Risiko | `frontend/src/components/Posts.jsx` | L |
| 4 | A-Modularität | 🟡 HIGH | Kein `BotPort`/`MessengerAdapter`-Interface, Bot + Storage hardcoded | `backend/config.py:43-56`, `backend/services/brand_voice_storage.py` | M |
| 5 | F-DSGVO | 🟡 HIGH | Kein `DELETE /tenant/{id}` (Right-to-Deletion #106) | 0 Treffer in `backend/api/` | M |
| 6 | F-DSGVO | 🟡 HIGH | Kein Wizard-Consent-Modul (#73) — keine Einwilligung-Spalte, kein Endpoint | 0 Treffer für `consent\|gdpr\|dsgvo` | M |
| 7 | D-Doku | 🟡 HIGH | Keine OpenAPI/Swagger-Specs trotz 40+ API-Endpoints | 0 Treffer für `*.openapi.*\|swagger*` | S |
| 8 | E-Portabilität | 🟡 HIGH | v1-Path im v2-Code: `/opt/content-autopilot/data/youtube_cookies.txt` | `backend/api/activity.py:213` | S |
| 9 | B-YouTube | 🟡 MEDIUM | Keine `transcripts`-Tabelle — wahrscheinlich inline in `source_items` (keine Versionierung) | 0 Treffer in `backend/alembic/versions/` | M |
| 10 | C-Security | 🟡 MEDIUM | Kein URL-Whitelist für externe Fetches (YouTube, RSS, Podcast) — SSRF-Risiko (OWASP A10) | grep negativ | M |

---

## Quick-Wins (S, ≤ 1 Tag)

- **#1** Frontend-Init-Endpoint: `/api/tenant-init` liefert Tenant-Key serverseitig statt hardcoded localStorage
- **#2** `USER appuser` in alle Dockerfiles, `RUN groupadd -r app && useradd ...` in jedem Build-Stage
- **#7** FastAPI `/docs` aktivieren, `app.openapi()` in CI-Job extrahieren
- **#8** v1-Path durch `os.environ.get("YT_COOKIES_PATH", "...")` ersetzen
- Pin Docker-Base-Images mit Digest

## Mittelgroß (M, 1-3 Tage)

- **#4** `MessengerAdapter`-ABC + Factory (Telegram, WhatsApp), Plattform-Enums in `Plattform`-Tabelle
- **#5** + **#6** DSGVO-Quartet: Consent-Spalte + Wizard-Step + `DELETE /tenant/{id}` mit Cascade + `GET /tenant/{id}/export` (JSON)
- **#9** Migration `transcripts`-Tabelle: `source_item_id`, `text`, `language`, `provider`, `confidence`, `version`
- **#10** `ALLOW_LIST_DOMAINS` in `.env`, Validator vor jeder externen URL-Fetch-Operation

## Groß (L, ≥ 1 Woche)

- **#3** `Posts.jsx`-Refactoring auf 5 Sub-Komponenten (`PostEditor`, `PostPreview`, `PostPublishPanel`, `PostAnalyticsPanel`, `PostsList`)
- `StorageAdapter`-ABC + 3 Backends (Nextcloud, Local, S3) für Multi-Tenant-Storage
- ADR-Pipeline aufsetzen (`docs/adr/`) — initial 5 ADRs (LLM-Routing, Storage, Bot-Adapter, DSGVO-Cleanup, Approve-Flow)

---

## Soll-Ist-Diff zur Phase-1-Surface-Analyse

**Nicht möglich** — Phase-1-Doc nicht im Repo verfügbar (`META-Phase1-Surface-Analyse-2026-05-04.md` liegt im Cowork-Workspace, der für den Audit-Subagent nicht zugänglich war).

Empfehlung an Robert: Phase-1-Doc ins Repo (z.B. `docs/meta-audit-2026-05-04/PHASE1.md`) committen, dann zweiter Pass für den Diff.

---

## Methodik-Hinweise

- 4 parallele Explorer-Subagents (Haiku 4.5), max-4-Regel aus CLAUDE.md beachtet
- Jeder Subagent hat 2-3 Bereiche bearbeitet, alle Aussagen mit `file:line`-Belegen
- 0 Treffer wurden als "0 Treffer" dokumentiert, nicht als "wahrscheinlich nicht vorhanden"
- Issue NICHT geschlossen (Constraint #12 — Robert ist Gate)
- Robert reviewt + entscheidet welche Findings als neue Issues angelegt werden

## Acceptance-Status

- [x] 9 Audit-Files unter `docs/meta-audit-2026-05-04/` mit file:line-Belegen
- [x] `SUMMARY.md` mit Top-10 Findings + Quick-Wins
- [ ] Cowork-Auto-Review mit Verdict + Diff zur Phase-1-Surface-Analyse → blockiert (Phase-1-Doc fehlt)
- [ ] Robert reviewt + entscheidet welche Findings als neue Issues angelegt werden
