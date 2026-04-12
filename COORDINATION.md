# Koordination: Claude Code (Builder) ↔ Cowork (QA/Architekt)

## Kommunikationskanal: Gitea Issues

- **Cowork** erstellt Issues mit Label `cowork` fuer Auftraege, Feedback, Korrekturen
- **Claude Code** liest offene Issues vor jedem neuen Feature
- **Claude Code** kommentiert auf Issues mit Status und schliesst erledigte Issues
- **Cowork** ueberwacht Commits und Code-Qualitaet via Gitea

## Aktueller Stand

| Feature | Status | Commit |
|---------|--------|--------|
| Backend v2.0 | LIVE | 849c0f0 |
| Frontend v1 (Dashboard, Sources, Pipeline, Content, Calendar, Settings) | LIVE | 849c0f0 |
| Frontend Ideas Page | OFFEN | — |
| Frontend Feedback Page | OFFEN | — |
| Navigation Update | OFFEN | — |
| Responsive + Polish | OFFEN | — |

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
