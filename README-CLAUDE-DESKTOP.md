# Claude Desktop → Content Autopilot MCP

Verbinde Claude Desktop mit dem Content Autopilot. Dann kannst du direkt in Claude mit deiner Content-Pipeline arbeiten — keine React-App nötig.

## Verbindung einrichten

### Mac
Datei: `~/Library/Application Support/Claude/claude_desktop_config.json`

### Windows
Datei: `%APPDATA%\Claude\claude_desktop_config.json`

### Konfiguration

```json
{
  "mcpServers": {
    "content-autopilot": {
      "type": "sse",
      "url": "http://10.10.0.1:8180/sse",
      "headers": {
        "X-API-Key": "***REMOVED-TENANT-KEY***"
      }
    }
  }
}
```

Nach dem Speichern: Claude Desktop neu starten.

## Verfügbare Tools (13 total)

### Überblick
- `autopilot_dashboard` — Was ist neu? Wieviele Ideen warten?

### Videos & Pipeline
- `autopilot_list_videos` — Alle analysierten Videos, filterbar nach Status
- `autopilot_analyze_video` — Einzelnes YouTube-Video manuell starten

### Content-Ideen
- `autopilot_list_ideas` — Ideen nach Relevanz, filterbar
- `autopilot_get_idea` — Vollständige Idee mit Fragen + bisherigen Antworten
- `autopilot_generate_ideas` — 5-8 Ideen aus einem Video generieren

### Dialogic Workflow (neu — $0 Post-Generierung)
- `dialogue_list_items` — Items bereit für Dialogue (mit Analyse + smarten Fragen)
- `dialogue_get_context` — Vollständiger Kontext: Transkript, Analyse, smarte Fragen, Voice-Profil
- `dialogue_submit_answers` — Roberts Antworten speichern (wörtlich!)
- `dialogue_generate_post` — Post-Prompt für Claude oder Backend-LLM

### Posts & Freigabe
- `autopilot_submit_answer` — Antwort auf eine Ideen-Frage speichern
- `autopilot_generate_post` — Post-Varianten via Backend generieren
- `autopilot_approve_post` — Post freigeben

### Brand Voice
- `autopilot_get_voice_profile` — Aktuelles Voice-Profil laden
- `autopilot_start_onboarding` — Neues Voice-Profil aus Onboarding erstellen

## Dialogic Workflow (empfohlen)

Der Dialogic Workflow spart Requesty-Kosten: Claude generiert Posts direkt, kein externer LLM-Call.

```
1. dialogue_list_items       → Welche Items sind bereit?
2. dialogue_get_context      → Vollständiger Kontext + smarte Fragen laden
3. [Fragen im Gespräch stellen, Antworten sammeln]
4. dialogue_submit_answers   → Antworten wörtlich speichern
5. dialogue_generate_post    → Prompt für Claude (use_claude_direct=true)
6. [Claude generiert Post direkt in der Konversation]
7. autopilot_approve_post    → Freigegebenen Post speichern
```

## Troubleshooting

**MCP verbindet nicht:**
- VPN aktiv? Server ist nur über WireGuard (10.10.0.1) erreichbar
- Claude Desktop neu starten nach Config-Änderung
- Port 8180 erreichbar? `curl http://10.10.0.1:8180/sse`

**"No tools found":**
- API-Key korrekt? Aktuell: `***REMOVED-TENANT-KEY***`
- Container läuft? `docker compose -f docker-compose.v2.yml ps mcp-server-v2`

**Tool schlägt fehl:**
- Backend läuft? `curl http://10.10.0.1:8601/api/health`
- Logs: `docker compose -f docker-compose.v2.yml logs mcp-server-v2`
