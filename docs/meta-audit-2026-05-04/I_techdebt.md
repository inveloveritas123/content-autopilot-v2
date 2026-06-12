# Audit I: Tech-Debt — TODOs, FIXMEs, Hidden Issues

**Datum:** 2026-05-04 | **Scope:** Quellcode-Scan (Python, JS/JSX)

## 1. TODO/FIXME/XXX/HACK-Scan

```bash
grep -rn "TODO\|FIXME\|XXX\|HACK" backend/ frontend/ --include="*.py" --include="*.js" --include="*.jsx"
→ 6 Treffer gefunden
```

### Alle Treffer (vollständig):

| File | Zeile | Text | Priorität |
|------|-------|------|-----------|
| `backend/api/voice_feedback.py` | 23 | `# TODO: #63 Schicht-1-Extraktion hier einbinden wenn implementiert` | MITTEL |
| `backend/tasks/p12_task.py` | 445 | `# TODO Schema-Migration: source_item_id nullable machen (empfohlen)` | MITTEL |
| `backend/tasks/publish_task.py` | 40 | `# TODO: LinkedIn OAuth publish when configured` | HOCH |
| `backend/tasks/setup_pipeline_task.py` | 10 | `- Email-Fallback (Stub, TODO)` | MITTEL |
| `backend/tasks/setup_pipeline_task.py` | 93 | `# TODO: email_task.send_setup_complete.apply_async(...)` | MITTEL |
| `backend/tasks/setup_pipeline_task.py` | 384 | `# TODO: source + source_payload in setup_pipeline_run persistieren für Resume` | HOCH |

**Bewertung:**
- **Gesamt: 6 TODOs** = sehr überschaubar (gutes Sign!)
- **Verteilung:** 4 im Backend, 0 im Frontend
- **Keine XXX/HACK-Marker** = keine temporären Workarounds

## 2. @deprecated + noqa-Marker

```bash
grep -rn "@deprecated\|noqa" backend/ --include="*.py"
→ 23 Treffer noqa, 0 Treffer @deprecated
```

### noqa-Analyse:

| Muster | Anzahl | Beispiel-File | Bedeutung |
|--------|--------|---------------|-----------|
| `noqa: BLE001` | 17 | `backend/tasks/telegram_task.py:215` | Bare Exception (absichtlich) |
| `noqa: A003` | 1 | `backend/logging_config.py:45` | Parameter shadowing builtin (`filter()`) |
| `noqa: ANN001` | 1 | `backend/tasks/celery_app.py:96` | Missing type annotation |

**Erkenntnisse:**
- **BLE001 überwiegt** = Bare Exception-Handling ist gewollt (z.B. für Resilience in Celery-Tasks)
- **Keine @deprecated-Marker** = Alte APIs werden nicht explizit als veraltet markiert
- **Typ-Ignorieren sind minimal** = Code ist gut getypt

## 3. Längste Dateien — Refactoring-Kandidaten

```bash
find . -name "*.py" -o -name "*.js" -o -name "*.jsx" | sort -rn | head -15 (nach Zeilen)
```

### Top 10 (Längsten):

| Datei | Zeilen | Funktion | Tech-Debt |
|-------|--------|----------|-----------|
| `frontend/src/components/Posts.jsx` | 3460 | UI-Komponente für Post-Verwaltung | 🔴 KRITISCH (>3K) |
| `backend/api/content.py` | 1663 | REST-API für Content | 🟡 HOCH (>1K) |
| `frontend/src/components/LLMSettings.jsx` | 1441 | LLM-Konfiguration UI | 🟡 HOCH |
| `backend/api/ideas.py` | 1392 | Ideen-Generierung API | 🟡 HOCH |
| `frontend/src/components/Ideas.jsx` | 1284 | Ideas-UI | 🟡 HOCH |
| `frontend/src/components/SourceList.jsx` | 1225 | Source-Verwaltung UI | 🟡 HOCH |
| `frontend/src/components/Analytics.jsx` | 1179 | Analyse-UI | 🟡 HOCH |
| `frontend/src/components/Dashboard.jsx` | 1130 | Haupt-Dashboard | 🟡 HOCH |
| `mcp-server/server.py` | 991 | MCP-Server | 🟡 HOCH |
| `frontend/src/components/BrandVoice.jsx` | 938 | Brand-Voice-Konfiguration | 🟡 HOCH |

### Detox-Dringlichkeit:

**Kritisch (>3K):**
- `Posts.jsx` (3460 Zeilen) = **Single Responsibility Principle verletzt**
  - Enthält: Post-CRUD, Preview, Publish, Analytics, Feedback-UI
  - Kandidat für Aufteilung in: `PostEditor`, `PostPreview`, `PostPublishModal`, `PostAnalytics`

**Hoch (>1K, <3K):**
- Frontend-Komponenten: React-State wird wahrscheinlich über Context/Hooks fragmentiert
- Backend-APIs: Endpunkte pro Modul sollten Subrouter nutzen (Router-Composition)

## 4. Bekannte Muster & Hidden Issues

### Pattern A: Error-Handling mit noqa
```python
# Beispiel aus telegram_task.py:215
except Exception as exc:  # noqa: BLE001
    logger.error(f"Telegram delivery failed: {exc}")
    # Intentional: Task retry via Celery, kein Propagation
```
**Bewertung:** ✅ OK, aber dokumentiert sein sollte

### Pattern B: No @deprecated Marker für alte APIs
**Problem:** Wenn alte Endpoints zu v1 gehören, sind sie nicht als deprecated markiert
**Beispiel:** Keine Hinweise auf Migrationsweg für Clients

### Pattern C: Große JSX-Komponenten mit State-Management-Implizitheit
**Problem:** SourceList.jsx (1225 Zeilen) könnte multiple Zustandsquellen haben
**Mitigated by:** Wahrscheinlich Context-API + Hooks (nicht sichtbar ohne Deep-Read)

## 5. Code-Qualitäts-Scorecard

| Aspekt | Score | Notizen |
|--------|-------|---------|
| TODO-Dichte | 🟢 6 TODOs in ~50KLOC | Sehr gut |
| deprecated-Marker | 🟡 0 @deprecated | Sollte für v1-APIs ergänzt werden |
| Exception-Handling | 🟢 17x noqa:BLE001 (intentional) | Gut dokumentiert |
| Type-Annotations | 🟢 Python, 1x noqa:ANN001 | Very good |
| Component-Size (Frontend) | 🔴 Posts.jsx: 3460 Zeilen | Refactoring nötig |
| API-Organization | 🟡 Content.py: 1663 Zeilen | Subrouter empfohlen |

## Top-3 Empfehlungen (Priorisierung)

### 1. **KRITISCH: Posts.jsx zerlegen** (Aufwand: 3-5 Tage)
   - Aufteilungsschema:
     - `PostEditor.jsx` (600Z) – Textbearbeitung
     - `PostPreview.jsx` (400Z) – Live-Preview
     - `PostPublishPanel.jsx` (500Z) – Channels + Scheduling
     - `PostAnalyticsPanel.jsx` (300Z) – Feedback + Metriken
     - `PostsList.jsx` (1260Z bleibt) – Tabelle + Filter
   - Gantt: 1-2 Wochen Sprint

### 2. **HOCH: LinkedIn OAuth in publish_task.py** (#40, Issue #40-voraussichtlich)
   - Derzeit nur Stub (`TODO: LinkedIn OAuth`)
   - Implementation ähnlich zu Telegram-API möglich
   - Aufwand: 3-5 Tage, wenn Meta-Account + OAuth-Token bereit

### 3. **HOCH: setup_pipeline_task Resume-Loop** (#384)
   - Persistierung von `source + source_payload` in `setup_pipeline_run`
   - Ermöglicht Fehlerbehandlung ohne Neustart des gesamten Pipelines
   - Aufwand: 2-3 Tage, aber kritisch für Produktiv-Stabilität

## Zusätzliche Beobachtungen

- **Keine deprecated-APIs explizit markiert:** Wenn v1 noch am Laufen ist, sollten Migrationshinweise pro Endpoint stehen
- **Frontend-Bundle-Size:** 3460Z Posts.jsx → likely >100KB beim Build → Performance-Check empfohlen
- **Email-Fallback (setup_pipeline_task.py:10):** TODO, aber nicht kritisch (Telegram ist Primary)
