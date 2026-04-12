# Content Autopilot — MCP Server

Plattformunabhaengiger MCP-Server der die Content-Autopilot-Pipeline
fuer jeden AI-Client zugaenglich macht.

## Funktioniert mit

- Claude Desktop / Cowork
- ChatGPT (mit MCP-Support)
- Google Gemini (mit MCP-Support)
- Jeder zukuenftige MCP-kompatible Client

## Setup

### 1. Abhaengigkeiten installieren

```bash
pip install -r requirements.txt
```

### 2. Environment-Variablen setzen

```bash
export CONTENT_AUTOPILOT_URL="http://152.53.142.163:8501"
export CONTENT_AUTOPILOT_API_KEY="dein-tenant-api-key"
```

### 3. In Claude Desktop konfigurieren

`~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "content-autopilot": {
      "command": "python",
      "args": ["/pfad/zu/mcp-server/server.py"],
      "env": {
        "CONTENT_AUTOPILOT_URL": "http://152.53.142.163:8501",
        "CONTENT_AUTOPILOT_API_KEY": "dein-tenant-api-key"
      }
    }
  }
}
```

## Verfuegbare Tools

| Tool | Beschreibung |
|------|-------------|
| `autopilot_dashboard` | Ueberblick: neue Videos, wartende Ideen |
| `autopilot_list_videos` | Analysierte Videos auflisten |
| `autopilot_generate_ideas` | Ideen aus analysiertem Video generieren |
| `autopilot_list_ideas` | Content-Ideen nach Status filtern |
| `autopilot_get_idea` | Idee-Details mit Fragen laden |
| `autopilot_submit_answer` | Unternehmer-Antwort speichern |
| `autopilot_generate_post` | Post aus Antworten generieren |
| `autopilot_approve_post` | Post freigeben |
| `autopilot_get_voice_profile` | Brand-Voice-Profil laden |
| `autopilot_start_onboarding` | Brand-Voice-Onboarding |
| `autopilot_analyze_video` | Manuelle Video-Analyse starten |

## Der Workflow

```
1. Unternehmer: "Was gibt's Neues?"
   → autopilot_dashboard

2. AI: "3 neue Videos analysiert, 8 Ideen bereit!"
   → autopilot_list_ideas (status=new)

3. AI: "Die Top-Idee: 'Warum 80% falsch planen' — Soll ich dir dazu Fragen stellen?"
   → autopilot_get_idea (zeigt vorbereitete Fragen)

4. AI stellt Fragen natuerlich im Gespraech
   Unternehmer antwortet
   → autopilot_submit_answer (pro Antwort)

5. AI: "Hier sind 2 Post-Varianten:"
   → autopilot_generate_post

6. Unternehmer: "Variante 1, aber schaerfer."
   AI iteriert direkt im Gespraech (keine extra API-Kosten!)

7. Unternehmer: "Perfekt!"
   → autopilot_approve_post
```

## Multi-Tenant

Jeder Kunde bekommt einen eigenen API-Key.
Der Key wird im MCP-Server als Environment-Variable konfiguriert.
So hat jeder Kunde seine eigene Content-Pipeline,
aber alles laeuft auf einem gemeinsamen Backend.
