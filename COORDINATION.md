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
| Frontend Ideas Page | LIVE | 8be8459 | #2 closed |
| Frontend Posts Page | LIVE | f619059 | — |
| Frontend VoiceProfile Page | LIVE | 8be8459 | #1 closed |
| Frontend Feedback Page | LIVE | f619059 | — |
| Frontend Navigation/Layout v2 | LIVE | f619059 | — |
| Frontend Dashboard v2 (responsive) | LIVE | 8be8459 | #3 closed |
| api.js v2 + LLM Routing | LIVE | f619059 | #5 (tote endpoints) |
| Deploy v2 Frontend | LIVE | 8be8459 | #6 closed |
| Ideen-Generierung von Ideas-Seite | LIVE | 6e42ff8 | #4 closed |
| api.js Cleanup | LIVE | 6e42ff8 | #5 closed |

### Status-Legende
- **LIVE** = Deployed und verifiziert auf 152.53.142.163:8501
- **CODE COMMITTED** = Code im main Branch, aber noch nicht deployed (npm build + docker compose noetig)
- **OFFEN** = Noch nicht gebaut

## Offene Issues (Prioritaet)

Keine offenen Issues.

## Geschlossene Issues

- **#1** VoiceProfile Backend-Endpoint — erledigt in 8be8459
- **#2** RelevanceBar null-check — erledigt in 8be8459
- **#3** Dashboard responsive Breakpoints — erledigt in 8be8459
- **#4** Ideen-Generierung von Ideas-Seite — erledigt in 6e42ff8
- **#5** api.js tote Endpoints — erledigt in 6e42ff8
- **#6** Deploy v2 Frontend — erledigt in f619059 + 8be8459

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
