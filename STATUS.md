# Content Autopilot v2 — Status

## Letzte Aenderung: 2026-06-02

> 269 Commits auf main seit Phase-1-Bootstrap. Repo ist Single-Source-of-Truth auf
> github.com/inveloveritas123/content-autopilot-v2 (private). Deploy-Strategie hat
> sich auf "lokal aus GitHub bauen" umgestellt (zuvor Gitea-Registry).

| Phase | Titel | Status | Letzter Marker | Ergebnis |
|-------|-------|--------|----------------|----------|
| 1     | Fundament (Adapter + Monitor + Frontend) | done | 2026-04-12 | YouTube/RSS/Podcast/Web-Adapter live, dynamische Polling-Intervalle |
| 4.1   | Content-Kategorien als Tag-System (#145) | done | 2026-05-04 | Kategorie-Verteilung im Analytics-Dashboard |
| 4.2   | 3 Aufhaenger-Varianten (#147) | done | 2026-05-04 | Backend + Frontend + Tests |
| 4.3/4.4 | Auto-Variants nach Idea + P05 Branchen-Scoring (#141) | done | 2026-05-04 | Industry-Boost in Pipeline + P12-Detail-Pass + 22 neue Tests |
| 5.1   | pgvector + memory_chunks (#140) | done | 2026-05-04 | Unternehmensgedaechtnis-Schema, Dim 1536 |
| 5.2   | Embedding-Service + Klassifikator (#140) | done | 2026-05-04 | Embedding-Pipeline aktiv |
| 5.3   | Telegram-Voice-Pipeline -> memory_chunk (#140) | done | 2026-05-04 | Voice-Memos werden vektorisiert eingebunden |
| 5.4   | Foto-Pipeline mit Tesseract-OCR (#140) | done | 2026-05-04 | OCR + Vision-LLM (Vertex/OpenAI) fuer describe_image |
| 5.5   | WhatsApp-Adapter-Stub + Channel-Awareness (#140) | stub | 2026-05-04 | Vorbereitet, nicht produktiv |
| 5.6   | Memory-API + Picker-UI + Sidebar (#140) | done | 2026-05-04 | UI-Zugriff aufs Unternehmensgedaechtnis |
| 5-Sub | Embedding-Versioning + Chunker + Quality-Gate-Eval (#150 #151 #152) | done | 2026-05-05 | Re-Embedding-Pfad + Eval-Runner |
| 6.1   | P07 Themen-Research mit Hook-Vorschlaegen (#141) | done | 2026-05-04 | Recherche-Pass mit Aufhaenger-Generierung |
| 7.4   | Hook-Library + Industry-Settings-UI (#142) | done | 2026-05-04 | P12-Allow-List + Track-Use |
| 8.x   | Onboarding-Profil + Vector-Viz + RtbF-DSGVO (#148 #149) | done | 2026-05-05 | DSGVO Art. 17 Cascade-Delete, Critical-Fixes Iter-2 PASS |
| Sprint 3A/B | 4 UX-Audits + Synthese (Top-3 pro Persona) | done | 2026-05-05 | META-Audit als Grundlage |
| Sprint 3C | 5 UX-Quick-Wins + alert()->toast Sweep | done | 2026-05-05 | Heatmap, Toast, Loading, Verben, Saeulen-Progress, 11 Files |
| Cost-Ops | Cost-Monitoring-Dashboard (#155) | done | 2026-05-05 | Trends + Cache-Hit-Rate + Runaway-Detection |
| Safety   | Pipeline-Pump-Throttle (#156) | done | 2026-05-05 | Defense-in-Depth gegen Runaway-Anomalien |
| META     | Top-3 Quick-Wins aus Audit (#157 #158 #159) | done | 2026-05-05 | Audit-Befunde umgesetzt |
| Docs     | 5 ADRs + 4 Runbooks + CONTRIBUTING + OpenAPI/Swagger | done | 2026-05-05 | Wissens-Backbone fuer Onboarding neuer Mitarbeiter |
| CI/CD    | Vitest + Frontend-Build-Check + Pytest-Gate + Gitleaks | done | 2026-06-01 | GitHub Actions Workflows aktiv |
| Deploy   | Deploy-from-GitHub Runbook + lokales Bauen als Standard | done | 2026-06-01 | docs/runbooks/deployment.md, Gitea/Registry optional |

## Constraints (festgeschrieben)

- **#12** Knecht schliesst NIE selbst — Robert ist Gate, auch nach Cowork-Approve
- **#13** Mobile-First/Telegram-First — Bot ist primaerer Touchpoint, Web sekundaer
- **#14** Soll-Ist-Pflicht + Subagent-UI-Test mit Browser-Use CLI 2.0 statt Playwright

## System-Status (2026-06-02)

- **v2 KOLONIE-Container** `content-autopilot` (10.30.0.136): 8 Docker-Services
  *up 5 days, healthy* — backend-v2, celery-worker-v2, celery-beat-v2,
  mcp-server-v2, nginx-v2, redis-v2 + nextcloud-web + nextcloud-app
- **Frontend** `http://10.10.0.1:8601` → HTTP 200
- **MCP** `:8180` erreichbar (root 404 ist erwartet, SSE-Endpoint live)
- **Gitea-Registry-Images** wurden am 2026-05-27 gebaut und enthalten alle
  Feature-Commits inkl. Phase 5/6/7/8 + Sprint 3C + Migration 049. Die 5
  GitHub-Commits danach (Security-Haertung, GitHub-Actions, Deploy-Doku,
  compose-Restructure auf "lokales Bauen Standard", Nextcloud-Migration) sind
  Build/Doku/CI ohne Runtime-Effekt — **kein Re-Build noetig**.
- **v1 Pitch Alpha** (:8501): aktuell nicht erreichbar — Status zu verifizieren.

## Phase 2 — Realstand

Anders als urspruenglich im FAHRPLAN-PDCA gelistet: **4 von 5 Punkten sind
gebaut**, nur unter Phase-Labels 4/5/6/8 verteilt:

| FAHRPLAN-Item | Status | Belegt durch |
|---------------|--------|--------------|
| Dialogischer Workflow E2E | done | `backend/api/wizard.py` (9 strukturierte Fragen q1_1..q5_*), `frontend/src/components/WizardPage.jsx` |
| Brand Voice Onboarding (9 Fragen) | done | Die 9 Wizard-Fragen oben + MD-Onboarding-Parser (`profile_md_parser.py`) als Alternative |
| Content Calendar | done | `frontend/src/components/ContentCalendar.jsx` + `tasks/random_smart_scheduler.py` (Cron mit 08-21 Operating-Hours-Guard) + Model `scheduled_post` |
| LinkedIn Auto-Upload | **bewusst offen** | `generate_linkedin_post_from_dialog` erzeugt das Format, `scheduled_post.linkedin_post_id` trackt — aber kein Auto-Posting an LinkedIn-API. **Konflikt mit Constraint #12 (Knecht schliesst NIE selbst, Robert ist Gate)** |
| Performance Tracking | done | `backend/api/analytics.py` + Model `content_performance` + Cost-Monitoring (#155) integriert in analytics |

## Naechste Schritte

1. **Entscheidung LinkedIn-Auto-Upload**: bewusst offen lassen (Constraint #12)
   oder mit explizitem Freigabe-Gate ("Robert klickt 'jetzt posten'") bauen.
2. **WhatsApp-Adapter** vom Stub zur produktiven Pipeline ausbauen (Phase-5-
   Welle-5 wurde nur als Stub markiert).
3. **v1 Pitch Alpha verifizieren** — Status :8501 klaeren, ggf. starten oder
   final eingefroren markieren.
4. **Container-Sync GitHub-Stand** ist erledigt (Filesystem auf 2026-06-02),
   `.old-20260602` kann nach Bestaetigung geloescht werden.

## Blocker

- Keine offenen Blocker auf main bekannt.
- Issues #157-#159 (META-Audit Quick-Wins) abgeschlossen — neue META-Iteration
  bei Bedarf einplanen.
