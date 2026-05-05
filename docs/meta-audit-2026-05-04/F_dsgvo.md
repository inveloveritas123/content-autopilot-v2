# DSGVO-Audit — content-autopilot-v2 (2026-05-04)

## Befund

### ✅ Audit-Logs vorhanden
**`backend/models/llm_call_log.py:13`** — `LLMCallLog` Tabelle existiert  
- Feldzuordnung: `tenant_id`, `model`, `task_type`, `prompt_tokens`, `completion_tokens`, `cost_cents`, `duration_ms`
- DB-Index: `idx_llm_call_logs_tenant_date` auf (`tenant_id`, `created_at`)
- **Wichtig:** Personenbezogene Prompts/Responses NICHT geloggt (nur Metadaten)

### ❌ Wizard-Consent-Modul (#73)
**0 Treffer:** Keine `consent`-Spalte, kein Endpoint `/consent`, keine Einwilligung-UI
- `grep -rn "consent|einwilligung|gdpr|dsgvo"` → kein Match

### ❌ Right-to-Deletion (#106)
**0 DELETE-Endpunkte für Tenants:**
- Existierende DELETEs: Reservoirs, Scheduling Posts, Projects, Sources (Ressourcen)
- `backend/api/` → kein `DELETE /tenant/{id}` oder `DELETE /api/tenants/{id}`
- Kein `delete_tenant()` Service implementiert

### ⚠️ Data-Export
**0 Treffer:** Kein `GET /tenant/{id}/export` oder ähnlicher Endpunkt  
- Keine CSV/JSON-Export-Funktion für Tenant-Daten sichtbar

### ✅ Cache-Kontrolle
**`backend/services/layer1_extraction.py:262`** und **`backend/services/p08_service.py:261`**
- Cache ist **ephemeral** (`"type": "ephemeral"`) — TTL kurz, personenbezogene Daten nicht persistiert
- DSGVO-Risk: **MINIMAL** (Cache-Tokens werden in `llm_call_logs` getracked, aber nur read/write counts, nicht Inhalte)

---

## Top-3-Empfehlungen

1. **Right-to-Deletion implementieren:** Endpoint `DELETE /api/tenants/{tenant_id}` mit Cascade-Delete (alle Einträge, Logs, Uploads) → Issue #106
2. **Consent-UI vor Beta:** Wizard mit explizitem Einwilligung-Checkpoint vor erstem LLM-Call (Audit-Trail in `llm_call_logs.user_consent_given`)
3. **Data-Export API:** `GET /api/tenants/{id}/export` (JSON) für Subj-Access-Requests — DSGVO Art. 15
