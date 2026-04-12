# Koordination: Claude Code (Builder) ↔ Cowork (QA/Architekt)

## Kommunikationskanal: Gitea Issues

- **Cowork** erstellt Issues mit Label `cowork` fuer Auftraege, Feedback, Korrekturen
- **Claude Code** liest offene Issues vor jedem neuen Feature
- **Claude Code** kommentiert auf Issues mit Status und schliesst erledigte Issues
- **Cowork** ueberwacht Commits und Code-Qualitaet via Gitea

## Aktueller Stand (2026-04-12)

| Feature | Status | Commit | Issues |
|---------|--------|--------|--------|
| Backend v2.0 | LIVE | 849c0f0 | — |
| Frontend v1 (Dashboard, Sources, Pipeline, Content, Calendar, Settings) | LIVE | 849c0f0 | — |
| Frontend Ideas Page | CODE COMMITTED | via Gitea MCP | #2 (null-check), #4 (generate trigger) |
| Frontend Posts Page | CODE COMMITTED | via Gitea MCP | — |
| Frontend VoiceProfile Page | CODE COMMITTED (blockiert) | via Gitea MCP | #1 (endpoint fehlt) |
| Frontend Navigation/Layout v2 | CODE COMMITTED | via Gitea MCP | — |
| Frontend Dashboard v2 | CODE COMMITTED | via Gitea MCP | #3 (responsive) |
| api.js v2 + LLM Routing | CODE COMMITTED | via Gitea MCP | #5 (tote endpoints) |
| Responsive + Polish | OFFEN | — | #3 |
| Deploy v2 Frontend | OFFEN | — | #6 |

### Status-Legende
- **LIVE** = Deployed und verifiziert auf 152.53.142.163:8501
- **CODE COMMITTED** = Code im main Branch, aber noch nicht deployed (npm build + docker compose noetig)
- **OFFEN** = Noch nicht gebaut

## Offene Issues (Prioritaet)

1. **#1 [HIGH]** VoiceProfile Backend-Endpoint fehlt — Seite zeigt leere Daten
2. **#6 [HIGH]** Deploy v2 Frontend — Eric sieht noch v1
3. **#2 [MEDIUM]** RelevanceBar crasht bei null Score + Ideas Array-Guard
4. **#3 [MEDIUM]** Dashboard responsive Breakpoints fehlen
5. **#4 [MEDIUM]** Ideen-Generierung von Ideas-Seite aus ermoeglichen
6. **#5 [LOW]** api.js tote Endpoints aufraeumen

## Empfohlene Reihenfolge fuer Claude Code

1. Zuerst #2 fixen (schnell, verhindert Crashes)
2. Dann #3 fixen (schnell, responsive Breakpoints)
3. Dann #6 deployen (git pull, npm build, docker compose)
4. Dann #1 angehen (Backend-Endpoint fuer VoiceProfile)
5. Dann #4 (UX-Verbesserung Ideas)
6. Zuletzt #5 (Cleanup)

## Rollen

**Claude Code (Server B)** = Builder
- Baut Features, testet, deployed, committed
- Checkt Issues vor jedem neuen Feature
- Meldet Fortschritt als Issue-Kommentar

**Cowork (Windows)** = QA + Architekt
- Ueberwacht Code-Qualitaet via Gitea (Commits, Dateien lesen)
- Gibt Feedback als neue Issues
- Priorisiert was als naechstes gebaut wird
- Prueft ob Backend-Endpoints korrekt angesprochen werden
