# Content Autopilot v2 — Handoff für Claude Cowork

> **Stand:** 2026-05-02 | **Autor:** Claude Code (Builder Session)

---

## 1. System-Status (LIVE)

Alle 6 Container laufen stabil:

| Container | Status | Port |
|-----------|--------|------|
| backend-v2 | Up ~20h | intern |
| celery-worker-v2 | Up ~20h | — |
| celery-beat-v2 | Up ~20h | — |
| mcp-server-v2 | Up ~20h | :8180 (VPN) |
| nginx-v2 | Up ~20h | :8601 (VPN) |
| redis-v2 | Up ~20h (healthy) | intern |

**Zugänge:**
- Frontend: `http://10.10.0.1:8601` (nur per VPN: 10.10.0.0/24)
- API Auth: `X-API-Key: ***REMOVED-TENANT-KEY***`
- Health-Check: `curl -sf http://localhost:8601/api/health` → `{"status":"ok","version":"2.0.0"}`

**Live-Daten im System (2026-05-02):**
- 4.267 Items gesammelt, 72 neu in 24h
- 1.848 Content-Ideen generiert
- 2.518 Posts approved, 4.851 Drafts, 1 published
- Pipeline aktiv (Celery-Beat pollt alle Quellen mit dynamischen Intervallen)

---

## 2. Was gebaut wurde (abgeschlossen)

### Phase 1 (KW 16–17) — KOMPLETT

| Feature | Commit | Status |
|---------|--------|--------|
| RSS-Adapter (feedparser + readability) | 4b1425b | ✅ tested, 50 Artikel mit Volltext |
| Podcast-Adapter (RSS + audio_url) | 4b1425b | ✅ 2826 Episoden |
| WebScraping-Adapter (Change Detection) | 4b1425b | ✅ läuft |
| Monitor-Task (dynamische Intervalle/Source) | 4b1425b | ✅ |
| Frontend Source-Management (Tabs, Cards) | 96e5bfc | ✅ |
| YouTube Video-Suche + Quellen-Entdecken Tab | 96e5bfc | ✅ |
| Retry-Buttons + Handwerker-Quellen-Presets | 0397aed | ✅ |
| Pipeline Blocker-Fixes (LLM 401 fallback, Ideation) | 13ed1be | ✅ |
| RSS Truncation-Fix, YouTube 4-Step Fallback | 4b1425b | ✅ |
| Voice Profile vollständig in Ideen-Prompts | 9cb679f | ✅ |
| Gemini Model Update (vertex/gemini-2.5-flash-lite) | b7f54cc | ✅ |
| max_tokens erhöht für Analyse + Fragen | 1f220ef | ✅ |

### Neuere Features (PDCA-Zyklen seit KW 17)

| Feature | Commit | Status |
|---------|--------|--------|
| SHK Hashtag Picker | 7eaefe6 | ✅ |
| Carousel-Templates | 7eaefe6 | ✅ |
| URL-Validation bei Source-Anlage | 7eaefe6 | ✅ |
| Analytics: Model Recommendations + Confidence | 2a4d329 | ✅ |
| Voice Profile: Testmatrix Demo-Preview + Live-Compare | 533cffa | ✅ |
| Post Review Dashboard (Eric-Daten) | 9eb2bc6 | ✅ |
| Knecht-Protokoll (Dual-Agent + LLM Routing S1–S6) | a5b8819 | ✅ |
| batch_transcribe mit needs_voicescriptor | 2553136 | ✅ |

---

## 3. Was noch offen ist

### Priorität 1 — E2E Workflow nie vollständig getestet

Der **dialogische Kernworkflow** (Idee → Fragen → Unternehmer antwortet → Post generiert) ist API-seitig implementiert, aber wurde **nie end-to-end im echten Betrieb durchgeklickt**.

Endpoints existieren:
- `GET /api/ideas` — Ideen abrufen ✅
- `POST /api/ideas/{id}/answer` — Antworten speichern ❓ nie getestet
- `POST /api/ideas/{id}/generate-post` — Post generieren ❓ nie getestet

**Nächster Schritt:** Eine Idee aus der Liste nehmen, alle 3 Fragen beantworten, Post generieren, Qualität bewerten.

### Priorität 2 — Phase 2 Features (laut SCOPE.md)

| Feature | Status | Aufwand |
|---------|--------|---------|
| Brand Voice Onboarding (vollständig) | UI-Skeleton, Backend-Endpoint da | M |
| Content Calendar | nur UI-Skeleton | M |
| Post-Vorschau (LinkedIn-Look/WYSIWYG) | fehlt | S |
| Best-Time-to-Post | fehlt | S |
| Hook-Bibliothek für Post-Einstiege | fehlt | S |

### Priorität 3 — Qualität / Tech Debt

| Punkt | Details |
|-------|---------|
| Mobile Responsiveness | nie auf 375px getestet |
| Error States | falsche URLs, leere Felder, API-Timeouts provozieren |
| Transcription Failed (168 Items) | Fehlerursache unklar, Retry-Logik prüfen |
| Auth/Multi-Tenant | nur API-Key, kein JWT |
| LinkedIn API | Performance Tracking manuell |

### Offene Gitea Issues

- **#37** 🔴 PDCA-Dauerschleife — Dauerauftrag: Konkurrenz-Features, Klick-Orgien, Scope-Kontrolle

---

## 4. Was NICHT angefasst werden darf

- `/opt/zukunftsbund-content-autopilot/` — Pitch Alpha v1 (EINGEFROREN, Demo für Eric)
- LiteLLM auf :4000
- PostgreSQL Config
- UFW/iptables
- Ports außer 8601 und 8180

---

## 5. Wichtige Befehle

```bash
# Health-Check
curl -sf http://localhost:8601/api/health

# API testen
curl -sf -H 'X-API-Key: ***REMOVED-TENANT-KEY***' http://localhost:8601/api/dashboard
curl -sf -H 'X-API-Key: ***REMOVED-TENANT-KEY***' http://localhost:8601/api/ideas?limit=5
curl -sf -H 'X-API-Key: ***REMOVED-TENANT-KEY***' http://localhost:8601/api/sources

# Container-Status
cd /opt/content-autopilot-v2
docker compose -f docker-compose.v2.yml ps

# Logs
docker compose -f docker-compose.v2.yml logs backend-v2 --tail 30
docker compose -f docker-compose.v2.yml logs celery-worker-v2 --tail 20

# Backend neu bauen + deployen
docker compose -f docker-compose.v2.yml build backend-v2 celery-worker-v2 celery-beat-v2
docker compose -f docker-compose.v2.yml up -d --force-recreate backend-v2 celery-worker-v2 celery-beat-v2

# Frontend bauen (IMMER auf Host, NICHT im Docker!)
cd /opt/content-autopilot-v2/frontend
npm run build
cd /opt/content-autopilot-v2
docker compose -f docker-compose.v2.yml build nginx-v2
docker compose -f docker-compose.v2.yml up -d --force-recreate nginx-v2

# Offene Issues checken
curl -sf 'http://localhost:3000/api/v1/repos/meister/content-autopilot-v2/issues?state=open&token=***REMOVED-GITEA-TOKEN***' | python3 -m json.tool
```

---

## 6. Architektur-Kontext (Knecht-Protokoll / LLM Routing)

Seit Commit `a5b8819` gibt es ein **Dual-Agent + LLM-Routing-System (S1–S6)**:
- S1–S2: Gemini Flash (Analyse, Transkription) — günstig
- S3–S4: Claude Sonnet (Creative Content) — Hauptmodell
- S5–S6: Claude Opus / Gemini Ultra (komplexe Tasks) — teuer, selten

Knecht-Protokoll: `CLAUDE.md` im Projektroot beschreibt die Rollen (Builder/Cowork).

---

## 7. Empfehlung für den nächsten Zyklus

1. **E2E-Test durchführen**: Eine Idee nehmen → alle Fragen beantworten → Post generieren → Qualität bewerten
2. **Klick-Orgie** gemäß Issue #37-Checkliste: jeden Tab, jeden Button, jeden Error State
3. **LinkedIn Post-Vorschau** bauen (WYSIWYG) — höchster Impact für Eric, kleiner Aufwand
4. **Content Calendar** fertigstellen
5. **COORDINATION.md** updaten (ist noch auf Stand 2026-04-12)
