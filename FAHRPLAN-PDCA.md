# Content Autopilot v2 — Fahrplan mit PDCA-Zyklus

> **Stand:** 12. April 2026

---

## Grundprinzip

Jedes Feature durchlaeuft: PLAN -> DO -> CHECK -> ACT
Kein Issue wird geschlossen ohne Test-Evidenz.
Bugs werden sofort als Gitea Issue erfasst.
STATUS.md im Repo wird nach jedem Issue aktualisiert.

---

## PDCA Konkret

### PLAN
- Issue lesen, Dateien identifizieren
- Ansatz als Issue-Kommentar dokumentieren
- Bei Architektur-Entscheidungen: Label "frage" + warten

### DO
- Feature-Branch: git checkout -b feature/issue-NR-beschreibung
- Atomare Commits mit Issue-Referenz: git commit -m "feat: #NR beschreibung"

### CHECK (PFLICHT)

| Stufe | Wie | Pflicht? |
|-------|-----|----------|
| Unit | pytest backend/tests/ -v | Ja, Backend |
| API | curl + Assertions | Ja |
| Integration | pytest + Celery | Ja, Pipeline |
| MCP | curl SSE :8180 | Ja, MCP-Aenderungen |
| Frontend | Manuell/Screenshot | Ja, UI |
| Smoke | docker ps + curl health | Immer |

### ACT
- Test OK: Kommentar + Close + Merge
- Test FAIL: Bug-Issue mit Label "bug"
- Unklar: Kommentar + Label "frage"

---

## Eskalationsstufen

1. Auto-Fix: Triviale Fehler sofort beheben
2. Bug-Issue: Nicht-triviale Fehler dokumentieren
3. Frage-Issue: Architektur-Entscheidung -> warten auf Robert
4. Notfall: v1 betroffen -> SOFORT STOPPEN + Label "kritisch"

---

## STATUS.md (PFLICHT nach jedem Issue)

```markdown
# Content Autopilot v2 — Status

## Letzte Aenderung: [Datum]

| # | Titel | Status | Letzter Test | Ergebnis |
|---|-------|--------|-------------|----------|
| 1 | Deploy | ... | ... | ... |

## Bekannte Bugs
## Naechste Schritte
## Blocker
```

---

## Phase 1: Fundament (KW 16-17)

Woche 1 (KW 16):
- Mo: #8 Bootstrap (Repo klonen)
- Mo-Mi: #1 Deploy (docker-compose.v2.yml, DB, VPN, Smoke-Test)
- Do-Fr: #2 Source-Model (Migration, Schema, API)

Woche 2 (KW 17):
- Mo: #3 RSS-Adapter
- Di: #4 Podcast-Adapter
- Mi: #5 WebScraping-Adapter
- Do: #6 Monitor-Task generalisieren
- Fr: #7 Frontend + Gesamttest

## Phase 2: Workflow und UX (KW 18-20)

- Dialogischer Workflow E2E
- Brand Voice Onboarding (9 Fragen)
- Content Calendar
- LinkedIn Auto-Upload
- Performance Tracking

## Phase 3: Intelligence (KW 21-24)

- pgvector Themen-Clustering
- Dynamic Few-Shot
- Messenger (Telegram/WhatsApp)
- Instagram Cross-Posting
- Newsletter-Generator

---

## Subagenten-Strategie

- Subagent 1: Backend (FastAPI, SQLAlchemy, Celery)
- Subagent 2: Frontend (React, Tailwind)
- Subagent 3: DevOps (Docker, nginx, UFW, DB)

Parallele Arbeit bei #3 + #4 + #5 (unabhaengig nach #2).

---

## Auto-Aktionen (kein Warten)

- Triviale Bug-Fixes
- Test-Ausfuehrung + Dokumentation
- STATUS.md Update
- Container Restart
- Alembic Migration
- npm/pip install

## Braucht Abstimmung (Label "frage")

- Neue DB-Tabellen / grosse Schema-Aenderungen
- Neuer LLM-Provider / Prompt-Strategie
- MCP-Tool-Signaturen aendern
- Neue Ports / Netzwerk
- Alles was v1 betreffen koennte
- Groessere Frontend-Redesigns

---

*Erstellt am 12. April 2026 | Content Autopilot v2*
