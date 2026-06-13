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
**Befund (Architekt, Gegencheck mit Louis-Übergabe):** Die v2-Datei ist **byte-identisch** mit Louis'
Original (`Import/Linkedin-Content-Autopilot/prompts/P17 prompt-kundenkontext-update.md`, 268 Zeilen) →
**kein v2-Transkriptionsfehler**, sondern Louis' eigene „Block"-Konvention (`## Block 1: PROMPT_ROLLE
(System-Prompt …)`, `## Block 2: KUNDENKONTEXT (…injiziert)`, `## Block 3: OUTPUT_FORMAT`). **P17 ist der
EINZIGE Nicht-Konformer** — P01/P03/P04/P08/… nutzen alle `## System-Prompt` / `## User-Prompt`.
Der Loader (`prompt_loader._extract_system_prompt`) keyt eindeutig auf `^## System-Prompt`; P17 hat das nicht
→ leerer System-Prompt → `prompt_health`=WEIRD → #41-Beobachter fail-opent (`skipped/prompt_unavailable`).
**Konkreter Vorschlag (minimal, braucht Chris/Robert-Freigabe da Template-Change):**
- P17 an die **Haus-Konvention** angleichen (wie die 12 anderen Prompts): `## System-Prompt` direkt vor
  „Block 1: PROMPT_ROLLE" einfügen; `## User-Prompt` bei „Block 2: KUNDENKONTEXT (…injiziert)" mit
  Platzhalter `{context_json}`. „Block 3: OUTPUT_FORMAT" bleibt inhaltlich im System-Block. **Wortlaut/Inhalt
  bleibt unverändert** — nur 2 Überschriften ergänzt.
- Architekt-Confidence **hoch** (Loader keyt eindeutig auf die Headings). Alternative „Loader lernt
  Block-Konvention" **verworfen**: fragiler Spezialfall nur für diese eine Datei.
- Output-Kontrakt (den der #41-Beobachter erwartet) unten — sollte in den `## User-Prompt`/Block-3-Teil.

**✅ Getestete Proposal-Kopie liegt vor:** `docs/chris-proposals/P17-kundenkontext-update--ANGEPASST-v1.md`
(Original **unangetastet**). Inhalt = Louis' Datei + 2 Loader-Überschriften (`## System-Prompt` vor Block 1,
`## User-Prompt` mit `{context_json}`). **Per Loader-Logik verifiziert:** System-Prompt 0→**8039** Zeichen,
User-Prompt 0→**276** Zeichen (mit `{context_json}`), Louis' Block-Wortlaut **unverändert**.
→ **Chris muss nur diese 2 Überschriften freigeben**, dann werden sie 1:1 ins Original übernommen und #41 schaltet scharf.
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

## ✅ Abgestimmt / erledigt / weggelassen (2026-06-13)
- **#22 P17-Headings — ERLEDIGT** (Robert: Chris-Freigabe nicht nötig). 2 Loader-Überschriften ins
  Original (Commit bc29724), versioniert in `docs/PROMPT-CHANGELOG.md`. #41-Prompt-Gate greift.
- **#39 / P02-Prompt — WEGGELASSEN** (Robert): P02 gab es nie (nicht bei Louis), wird nirgends im Code
  referenziert → kein Prompt nötig, Feature deferiert.
- **#36 / #44 — non-blocking:** Lesarten (4.6/4.7) + neue Phasen laufen mit board-konformen Defaults;
  Verfeinerung jederzeit möglich, **blockiert nichts**. Robert: „eigentlich nichts von Chris zu entscheiden."

## 🟡 Workflow für künftige Prompt-Anpassungen (Robert-Wunsch)
Anpassungen an Prompts werden **versioniert im GH** geführt: Änderung in `content-truth/prompts/…`,
Eintrag in `docs/PROMPT-CHANGELOG.md` (Version + Datum + exakte Änderung), Commit `[arch] fix(prompt)…`.

---
*Architekt trägt hier ein, sobald ein Prompt-/MD-Punkt Chris-Abstimmung braucht. Originale werden NICHT
ohne Freigabe verändert.*
