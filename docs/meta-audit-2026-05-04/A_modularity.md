# Audit A: Modularität — Bot-Adapter, Storage, LLM

**Datum:** 2026-05-04 | **Scope:** Quellcode-Review (keine Plan-Dokumente)

## 1. Bot-Adapter / Messenger-Spezifikalität

### Grepped: Telegram & WhatsApp hardcoded

```bash
grep -rn "telegram\|whatsapp\|bot_port\|BotPort\|MessengerWebhook" backend/ (102 Treffer)
```

**Findings:**

1. **Telegram-Konfiguration** (`backend/config.py:43-46`)
   - `telegram_bot_token`, `telegram_admin_chat_id`, `telegram_webhook_secret`
   - NICHT ENV-konfigurierbar, ENV-Fallback nur via Pydantic

2. **WhatsApp-Konfiguration** (`backend/config.py:53-56`)
   - `whatsapp_access_token`, `whatsapp_phone_number_id`, `whatsapp_verify_token`, `whatsapp_app_secret`
   - Separate Implementierung in `backend/api/whatsapp.py`

3. **Keine Bot-Port-Abstraktion**
   - grep ergab: 0 Treffer für `BotPort`, `MessengerWebhook`, `MessengerAdapter`
   - Telegram + WhatsApp sind **direkt in der FastAPI-API implementiert**, nicht über ein generisches Interface

4. **Quellen-spezifische Typen** (`backend/alembic/versions/038_memory_chunks_pgvector.py:25-28`)
   ```python
   SOURCE_TYPES = (
       "voice_telegram",
       "voice_whatsapp",
       "photo_telegram",
       "photo_whatsapp",
       ...
   )
   ```
   → Plattformen sind als Enum-Werte hardcoded, nicht dynamisch erweiterbar

### Fazit zur Modularität (Bot)
**Architektur: ❌ NICHT modular**
- Jeder neue Messenger erfordert:
  - Neuen API-Endpoint in `backend/api/`
  - Neue Enum-Werte in Migrations
  - Neue Config-Felder in `settings`
- **Empfehlung:** Adapter-Pattern mit generischem `MessengerAdapter`-Interface + Registry

---

## 2. Storage-Adapter

### Dateisuche: storage_adapter.py

```bash
ls -la backend/services/ | grep -i storage
→ brand_voice_storage.py (16.6 KB)
  (Keine storage_adapter.py, keine abstrakte Storage-Schicht)
```

**Findings:**

1. **Keine abstrakte Storage-Klasse**
   - `brand_voice_storage.py` ist **Nextcloud-spezifisch**, nicht generisch
   - Größe: 16.6 KB (Produktiv-Code, keine Skelett)

2. **Nextcloud hardcoded in mehreren Services:**
   - `backend/config.py:34-36`: `brand_voice_nc_base_path`, `prompt_nc_base_path`
   - `backend/services/brand_voice_storage.py`: direkte WebDAV-Calls zu Nextcloud

3. **Keine lokale/S3/GCS-Alternative:**
   - grep nach `boto3`, `s3`, `gcs`, `minio`: 0 Treffer in backend/services/

### Fazit zur Modularität (Storage)
**Architektur: ❌ NICHT modular**
- **Locked-in zu Nextcloud** – kein lokaler Fallback, kein S3-Support
- **Empfehlung:** `StorageAdapter`-ABC mit `NexCloudStorage`, `LocalFileStorage`, `S3Storage`

---

## 3. LLM-Provider-Auswahl

### Grep: LLM_PROVIDER & Provider-Imports

```bash
grep -rn "LLM_PROVIDER\|OPENAI_API_KEY\|requesty\|vertex\|gemini\|claude" backend/ --include="*.py"
(Top Treffer:)
- backend/config.py:14-18: gemini_api_key, anthropic_api_key, litellm_base_url, litellm_api_key, requesty_api_key
- backend/tasks/p01_task.py:136: estimate_vertex_cost (Vertex wird genutzt)
- backend/tests/test_voice_transcription.py:45: transcribe_with_gemini (Gemini direkt importiert)
```

**Findings:**

1. **Mehrere LLM-Provider unterstützt (theoretisch)**
   - Config: `gemini_api_key`, `anthropic_api_key`, `requesty_api_key`, `litellm_base_url`
   - Aber **keine ENV-Fallbacks**, nur Settings-Objekt → Environment-Variables müssen manuell gesetzt werden

2. **Routing nicht explizit dokumentiert**
   - `litellm_base_url` deutet auf LiteLLM-Proxy hin
   - grep nach `import litellm` oder `from litellm`: 0 Treffer
   - **Provider-Auswahl erfolgt wahrscheinlich im Backend-Code, nicht konfigurierbar**

3. **Hardcoded Vertex-Calls:**
   - `backend/tasks/p01_task.py:136` nutzet `estimate_vertex_cost` direkt
   - Keine Abstraktion über `LLMProvider`-Interface

### Fazit zur Modularität (LLM)
**Architektur: 🟡 TEILWEISE modular**
- Konfigurierbar: Gemini, Anthropic, LiteLLM-Proxy
- Hardcoded: Vertex (Cost-Cap), direkte Gemini-Calls in Tests
- **Empfehlung:** Einheitliches `LLMProvider`-Interface + Routing-Strategie dokumentieren (CLAUDE.md erwähnt bereits v2-Stack, aber nicht explizit im Code)

---

## Zusammenfassung Modularität

| Bereich | Status | Top-Issue |
|---------|--------|-----------|
| Bot-Adapter | ❌ Hardcoded (Telegram + WhatsApp) | Keine generische MessengerAdapter-Klasse |
| Storage | ❌ Nextcloud-locked | Keine abstrakte Storage-Schicht |
| LLM-Provider | 🟡 Teilweise (Config + Hardcoded) | Routing-Logik implizit, nicht transparent |

**Gesamtbewertung:** Codebase ist **für Production v2 ausreichend, aber nicht future-proof**. Jede neue Plattform/Storage/LLM erfordert Code-Änderungen statt nur Konfiguration.

**Top-3 Empfehlungen:**
1. `MessengerAdapter`-ABC + Factory für Telegram, WhatsApp, Signal, Discord (später)
2. `StorageAdapter`-ABC mit Nextcloud, Local, S3 (ermöglicht Multi-Tenant-Storage)
3. `LLMProvider`-Routing explizit machen: Config-basierte Model-Selection mit Fallback-Kette

