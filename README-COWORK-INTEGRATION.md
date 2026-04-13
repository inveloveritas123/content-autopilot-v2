# Cowork API Integration

Externe API für das Post-Review-Dashboard (Claude Cowork / Bauleiter).

**Base URL:** `http://10.10.0.1:8601/api/v1/cowork`

## Authentifizierung

Zwei Varianten werden akzeptiert:

```
X-API-Key: ***REMOVED-TENANT-KEY***
```
oder
```
Authorization: Bearer ***REMOVED-TENANT-KEY***
```

## Endpoints

### 1. Items auflisten

```
GET /api/v1/cowork/items
```

Query-Parameter:
- `status`: `transcribed` | `analyzed` | `content_ready` | `all` (default: transcribed+analyzed+content_ready)
- `limit`: 1–50 (default: 20)
- `offset`: Pagination

```bash
curl -H "x-api-key: ***REMOVED-TENANT-KEY***" \
  "http://10.10.0.1:8601/api/v1/cowork/items?status=analyzed&limit=10"
```

Response: `{ items: [...], total: 3840, limit: 10, offset: 0 }`

Jedes Item enthält: `id`, `title`, `source`, `status`, `summary_1sentence`, `word_count`, `tags`, `has_analysis`, `has_questions`, `has_post_draft`

---

### 2. Vollständiger Kontext

```
GET /api/v1/cowork/items/{id}/context
```

```bash
curl -H "x-api-key: ***REMOVED-TENANT-KEY***" \
  "http://10.10.0.1:8601/api/v1/cowork/items/{uuid}/context"
```

Response enthält:
- `transcript.full_text`, `excerpt_500_words`, `key_quotes`, `word_count`
- `analysis.main_topic`, `insights`, `hooks`, `relevance_score`
- `smart_questions[]` mit `id`, `question`, `transcript_reference`, `answer`
- `voice_profile`, `forbidden_phrases`
- `post_drafts` (nach Format)
- `previous_posts[]`

---

### 3. Status aktualisieren

```
PATCH /api/v1/cowork/items/{id}/status
```

```bash
curl -X PATCH \
  -H "x-api-key: ***REMOVED-TENANT-KEY***" \
  -H "Content-Type: application/json" \
  -d '{"status": "approved"}' \
  "http://10.10.0.1:8601/api/v1/cowork/items/{uuid}/status"
```

Gültige Status: `transcribed`, `analyzing`, `analyzed`, `generating`, `content_ready`, `approved`, `rejected`, `queued`, `uploaded`

---

### 4. Antworten speichern

```
POST /api/v1/cowork/items/{id}/answers
```

```bash
curl -X POST \
  -H "x-api-key: ***REMOVED-TENANT-KEY***" \
  -H "Content-Type: application/json" \
  -d '{
    "answers": [
      {"question_id": "uuid-der-frage", "answer_text": "Roberts Antwort..."}
    ]
  }' \
  "http://10.10.0.1:8601/api/v1/cowork/items/{uuid}/answers"
```

Response: `{ answers_saved: 1, questions_answered: 2, questions_pending: 1 }`

---

### 5. Post-Entwurf speichern

```
POST /api/v1/cowork/items/{id}/post
```

```bash
curl -X POST \
  -H "x-api-key: ***REMOVED-TENANT-KEY***" \
  -H "Content-Type: application/json" \
  -d '{
    "format": "story",
    "content": "Der fertige LinkedIn-Post-Text...",
    "approved": true,
    "user_edited": true
  }' \
  "http://10.10.0.1:8601/api/v1/cowork/items/{uuid}/post"
```

Response: `{ post_id: "uuid", saved: true, status: "approved", char_count: 847 }`

---

## JavaScript Beispiel (Dashboard)

```javascript
const API = 'http://10.10.0.1:8601/api/v1/cowork';
const KEY = '***REMOVED-TENANT-KEY***';
const headers = { 'x-api-key': KEY, 'Content-Type': 'application/json' };

// Items laden
const { items } = await fetch(`${API}/items?status=analyzed`).then(r => r.json());

// Kontext laden
const ctx = await fetch(`${API}/items/${items[0].id}/context`, { headers }).then(r => r.json());

// Antwort speichern
await fetch(`${API}/items/${items[0].id}/answers`, {
  method: 'POST',
  headers,
  body: JSON.stringify({
    answers: [{ question_id: ctx.smart_questions[0].id, answer_text: 'Meine Erfahrung...' }]
  })
});

// Post speichern
await fetch(`${API}/items/${items[0].id}/post`, {
  method: 'POST',
  headers,
  body: JSON.stringify({ format: 'story', content: 'Fertig geschriebener Post...', approved: true })
});
```

## CORS

Aktiviert für alle Origins — Dashboard kann direkt aufrufen ohne Proxy.

## API-Dokumentation

Interactive Docs: `http://10.10.0.1:8601/docs` → Abschnitt "Cowork"
