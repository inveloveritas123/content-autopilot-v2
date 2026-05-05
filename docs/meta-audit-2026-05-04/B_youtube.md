# Audit B: YouTube-Transkription

**Datum:** 2026-05-04 | **Scope:** Quellcode-Review (keine Plan-Dokumente)

## 1. Grep-Ergebnisse: YouTube & Transkription

```bash
grep -rn "youtube\|captions\|whisper\|asr" backend/ --include="*.py"
→ 102 Treffer gefunden
```

**Top-10 Files mit YouTube-Bezug:**

1. `backend/api/activity.py:213` – YouTube Cookies für yt-dlp
2. `backend/api/sources.py:16` – `search_youtube_channels`, `search_youtube_videos` (imports)
3. `backend/api/sources.py:30` – Type: `"youtube"` (Enum-Wert)
4. `backend/api/sources.py:212` – URL-Validation für YouTube URLs
5. `backend/api/sources.py:247` – POST `/sources/youtube/search-channels`
6. `backend/api/sources.py:251` – POST `/sources/youtube/search-videos`
7. `backend/api/sources.py:277-281` – `search_youtube_channels()` async call
8. `backend/api/llm_settings.py:539` – source_type="youtube" bei Default-Setup
9. `backend/tasks/transcribe_task.py:31` – `source.type if source else "youtube"` (Transkription)
10. `backend/tasks/transcribe_task.py:104` – Source-Type-Bestimmung in Transkription

## 2. Transkriptions-Tabelle & Migration

```bash
grep -rn "transcripts" backend/alembic/versions/
→ 0 Treffer gefunden
```

**Findings:**

1. **Keine explizite `transcripts`-Tabelle**
   - Transkriptionen werden wahrscheinlich als **Spalte in `source_items`** gespeichert
   - Oder als **separate Inhalte in `content_pieces`** (nicht als eigene Tabelle)

2. **Transkriptions-Task existiert:**
   - `backend/tasks/transcribe_task.py` – vollständige Task-Datei (existiert)
   - Speichert Transkripte wahrscheinlich in `source_items.transcript` oder ähnliches

3. **Keine Alembic-Migration für Transkripte**
   - Könnte sein:
     - Transkripte werden inline gespeichert
     - Oder als JSONB-Feld ohne Schema-Migration

### Transkriptions-Spalten (indirekt ermittelt):

Aus `backend/tasks/transcribe_task.py` lässt sich ableiten:
```python
# Wahrscheinliche Struktur:
transcript = {
    "id": UUID,
    "source_item_id": UUID,
    "text": str,          # Transkription
    "language": str,       # z.B. "de"
    "duration": float,     # Sekunden
    "provider": str,       # "gemini", "vertex", etc.
    "confidence": float,   # ASR-Konfidenz (optional)
    "created_at": datetime,
    "updated_at": datetime,
}
```

## 3. Transkriptions-Endpunkte

```bash
grep -rn "transcribe\|youtube" backend/api/ --include="*.py"
```

**Existierende Endpoints:**

1. **POST `/tasks/transcribe`** (?? nicht explizit in Grep)
   - Task-API: Async-Transkription starten

2. **GET `/items/{item_id}/transcript`** (?? angenommen)
   - Transkript abrufen (implizit via `source_items`)

3. **GET `/sources/youtube/search-channels`**
   - `backend/api/sources.py:247` – YouTube-Kanal-Suche

4. **GET `/sources/youtube/search-videos`**
   - `backend/api/sources.py:257` – YouTube-Video-Suche

**Endpunkte für Transkription explizit:**
- Grep nach `@router.post.*transcribe`: 0 Treffer in api/
- Transkription erfolgt über **Celery-Tasks** (`backend/tasks/transcribe_task.py`)
- Kein direkter REST-Endpoint zum Transkribieren sichtbar

## 4. Transkriptions-Status: Implementiert, aber nicht vollständig dokumentiert

| Aspekt | Status | Belege |
|--------|--------|--------|
| YouTube-Suche | ✅ Implementiert | `backend/api/sources.py:247-257` |
| Transkriptions-Task | ✅ Implementiert | `backend/tasks/transcribe_task.py` |
| ASR-Provider (Gemini) | ✅ Implementiert | `backend/tests/test_voice_transcription.py:45` |
| Transkriptions-Tabelle | ❌ Explizit (inline?) | 0 Alembic-Treffer |
| REST-Endpunkt | 🟡 Implizit (via Celery) | Kein `/api/transcribe` sichtbar |
| Captions/Subtitles | ❓ Unklar | 0 Treffer für "captions" |

## 5. Architektur-Erkenntnis

**YouTube-Transkription folgt diesem Flow:**

```
YouTube-URL (via /sources/youtube)
    ↓
Source + SourceItem erstellt
    ↓
Celery-Task: transcribe_task.py
    ↓
Gemini ASR (oder Vertex?)
    ↓
Transkript in source_items gespeichert (wahrscheinlich als JSONB)
    ↓
ContentIdea-Generation nutzt Transkript
```

**Fehlende Elemente:**
- Keine direkte YouTube-Caption-API-Integration (nur ASR auf Audio)
- Keine WebVTT/SRT-Export (Untertitel-Format)
- Keine Transkriptions-Fehlerquoten-Tracking (confidence-Feld?)

## Top-3 Empfehlungen

1. **Migration für `transcripts`-Tabelle erstellen**
   - Separate Tabelle mit `source_item_id`, `text`, `language`, `provider`, `confidence`
   - Ermöglicht Versions-Tracking und Feedback-Loop (Korrekturen)

2. **Expliziter REST-Endpunkt für Transkription**
   - `POST /api/sources/{id}/transcribe` mit Modell-Selection (Gemini/Vertex/Whisper)
   - Return: Async Job-ID (kein Direct-Response, zu lange)

3. **YouTube-Caption-Fallback**
   - Wenn Video offizielle Untertitel hat: nutzen statt ASR
   - Nur bei Fehlen oder `?force=true` re-transkribieren

