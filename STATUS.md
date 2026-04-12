# Content Autopilot v2 — Status

## Letzte Aenderung: 2026-04-12 17:58

| # | Titel | Status | Letzter Test | Ergebnis |
|---|-------|--------|-------------|----------|
| 8 | Bootstrap | done | 2026-04-12 | Repo analysiert, Docs gelesen |
| 1/10 | Deploy v2 | done | 2026-04-12 | 6 Container auf :8601/:8180, DB migriert |
| 3 | RSS-Adapter | done | 2026-04-12 | 50 Artikel mit Volltext via readability |
| 4 | Podcast-Adapter | done | 2026-04-12 | 2826 Episoden mit audio_url importiert |
| 5 | WebScraping-Adapter | open | - | - |
| 6 | Monitor-Task | open | - | - |
| 7 | Frontend Source-Mgmt | open | - | - |

## System-Status
- v2 Health: OK (:8601/api/health)
- v2 Frontend: 200 (:8601)
- v2 MCP: SSE erreichbar (:8180)
- v1 Pitch Alpha: LAEUFT (:8501)

## Bekannte Einschraenkungen
- Podcast Audio-Transkription E2E ungetestet (LiteLLM → Gemini Audio)
- 2826 Podcast-Items in DB (Test-Daten, ggf. bereinigen)

## Naechste Schritte
- #5 WebScraping-Adapter (HOCH)
- #6 Monitor-Task generalisieren (HOCH)
- #7 Frontend Source-Management (MITTEL)
