# Prompt-Changelog — versionierte Anpassungen an den Vorlagen

> Prompts liegen in `content-truth/prompts/` (Original-Hoheit Chris/Louis). Jede Anpassung hier
> mit Version + Datum + exakter Aenderung dokumentieren. Wortlaut-Aenderungen brauchen
> Chris/Robert-Freigabe; strukturelle Loader-Angleichungen werden hier protokolliert.

## P17-kundenkontext-update.md
- **v1.1 | 2026-06-13 | #22** (Freigabe Robert): Zwei Loader-Ueberschriften ergaenzt —
  `## System-Prompt` direkt vor "Block 1: PROMPT_ROLLE"; `## User-Prompt` vor "Implementation
  Notes" mit einem 3-Zeilen-Template, das `{context_json}` enthaelt (der #41-Beobachter injiziert
  dort Transkript + aktive Profile). **Louis' Block 1/2/3-Wortlaut unveraendert** (Reihenfolge
  Rolle->Kontext->Format bleibt). Grund: Loader extrahierte vorher einen leeren System-Prompt
  (P17 war der einzige Prompt ohne `## System-Prompt`-Heading).
- v1.0: Louis-Original (Uebergabe `Import/Linkedin-Content-Autopilot/`).
