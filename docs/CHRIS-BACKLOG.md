# CHRIS-BACKLOG — Prompt-/MD-Abstimmung (Content-Hoheit: Chris)

> **Grundregel (Robert, 2026-06-13):** Alle Vorlagen (Prompts, MD-Templates) liegen im GitHub-Repo und
> werden **nicht ohne Freigabe** von Chris/Robert verändert. Der Architekt fasst Originale nicht an —
> er **fail-opent** bei kaputten Prompts und legt hier **konkrete Vorschläge** ab (gerne mit getesteter
> Alternative als *separate* Datei), die Chris abstimmt und freigibt. Erst nach Freigabe wird das Original geändert.

> **Arbeitsweise:** Wo sinnvoll, testet der Architekt eine korrigierte Variante (neue Proposal-Datei, nie das
> Original) und hinterlegt das Ergebnis hier, damit die Entscheidung datenbasiert ist.

---

## 🔴 Offen — wartet auf Chris

### #22 — P17-Prompt lädt mit leerem System-Prompt (blockiert #41-Scharfschaltung)
**Datei:** `content-truth/prompts/P17-kundenkontext-update.md`
**Problem:** Nutzt Eigenkonstruktions-Headings (`## Block 1: PROMPT_ROLLE …`, `## Block 2/3`) statt der
Loader-Konvention `## System-Prompt` / `## User-Prompt` → `prompt_loader` liefert **leeren System-Prompt**
→ `prompt_health` meldet WEIRD. Der #41-Beobachter fail-opent deshalb (`skipped/prompt_unavailable`).
**Konkreter Vorschlag (zur Abstimmung):**
- Überschriften vereinheitlichen: `## System-Prompt` (Rolle/Regeln) + `## User-Prompt` (mit Platzhalter
  `{context_json}` und dem Output-Kontrakt unten). Inhalt/Wortlaut bleibt Chris.
- **Output-Kontrakt, den der #41-Beobachter erwartet** (Bucket-Form bevorzugt):
  ```json
  {
    "voice":  {"proposals": [{"field_path": "tonalitaet.grundton", "new_value": "...", "op": "set"}],
               "summary": "...", "confidence": 0.0-1.0},
    "values": {"proposals": [{"field_path": "werte", "new_value": "...", "op": "append"}], "summary": "...", "confidence": ...},
    "avatar": {"proposals": [...], "summary": "...", "confidence": ...}
  }
  ```
  Alternativ flache Liste mit `entity_type` je Proposal (wird ebenfalls verarbeitet). `op` = `set` (default)
  oder `append` (Listen-Felder wie `werte`).
**Status:** Architekt kann eine korrigierte Heading-Variante als Proposal-Datei + Loader-Test beilegen (auf Wunsch).

### #36 — Konversations-Lesarten (Board 4.6/4.7)
- **(a)** Board 4.6 „optional 2–3 Rückfragen VOR den Aufhängern" wurde im MVP übersprungen — die targeted-Session
  NACH der Wahl liefert die Rückfragen via Bahn 5. **Lesart bestätigen** oder Rückfragen vorziehen?
- **(b)** Aufhänger-Wahl per **Text-Nummern „1/2/3"** statt Telegram-Inline-Buttons (MVP). Bestätigen oder Buttons gewünscht?

### #44 — Wortlaut der neuen Gesprächsphasen (Wizard 6→8)
Die 2 neuen Board-Phasen sind strukturell drin (`api/wizard_phases.py`), aber mit **board-konformen Default-Fragen**.
**Chris:** finalen Frage-Wortlaut der neuen Phasen liefern/abstimmen.

### #39 — P02 Website-Analyse braucht Chris-Prompt
P02-Pfad wartet auf den Prompt-Wortlaut (Website-Quelle → Kontext). **Chris:** Prompt liefern.

---

## ✅ Abgestimmt / freigegeben
- (noch nichts)

---
*Architekt trägt hier ein, sobald ein Prompt-/MD-Punkt Chris-Abstimmung braucht. Originale werden NICHT
ohne Freigabe verändert.*
