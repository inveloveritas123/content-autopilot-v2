# ROBERT-BACKLOG — Entscheidungen & Freigaben (nur Mensch)

> Hier sammelt der Architekt alles, was **nur Robert** entscheiden/freigeben kann (DB-Migrationen, Provider/Modell-Wechsel, Merges nach main, Firewall/Secrets, Deploy). Der autonome Lauf legt Code dafür vor, **mergt/aktiviert aber nichts** davon selbst. Stand laufend aktualisiert.

## 🔴 Offen — wartet auf Robert

### Merges nach main (kein Selbst-Merge)
- **PR #55** `arch/weekloop` → main: #15 (p08/layer1 LLM-Seam) + #16 (Inbound-Routing) + #43-Konzept + Gesamtreport. Cross-Model-Review GRÜN, 47 Tests lokal grün. **→ review & merge.**
- **PR #53** `knecht/fix-33-json` (P01/P03 JSON-Output) — Knecht, blockiert #32 Eric-E2E. **→ review & merge.**
- **PR #54** `knecht/fix-47-ci-green` (CI main grün). **→ review & merge.**

### ~~#42 — Content-Modell-Entscheid~~ ✅ ENTSCHIEDEN 2026-06-13 (Testmodus, s.u. Erledigt)
### #42 — Content-Modell-Entscheid (dringend, betrifft alle kreativen Pfade)
Drei Realitäten: S6 = Sonnet-EU (Bedrock-Frankfurt) · kreative Pfade (ideation/questions) auf Gemini-Flash-Lite remappt · Seam-Bypässe = US-API (wird in #46 behoben).
- **Entscheidung A:** Board sagt „Opus für Content" — bleibt es bei Sonnet-EU als Default (EU-Souveränität schlägt Board-Buchstabe), Opus nur als CONFIRM-Upgrade? **Empfehlung Architekt: ja.**
- **Entscheidung B (dringender):** Der Gemini-Flash-Lite-Remap der kreativen Pfade revidieren (zurück auf ein stärkeres EU-Modell) oder bewusst bestätigen? **Empfehlung: revidieren** — widerspricht dem Board stärker als Sonnet-statt-Opus.

### ~~#43 — Werte-Entität: neue DB-Tabelle~~ ✅ FREIGEGEBEN 2026-06-13 (anwenden nach Landing; s.u. Erledigt)
### #43 — Werte-Entität: **neue DB-Tabelle** `tenant_customer_values` (freigabe-robert)
Konzept (`docs/CONCEPT-43-werte-entitaet.md`) + Plan (`docs/SPRINT-2-PLAN-43.md`) liegen vor.
**Migration `backend/alembic/versions/053_customer_values.py` ist GESCHRIEBEN, aber NICHT angewandt** (Kopfkommentar `freigabe-robert`). Inhalt: CREATE TABLE `tenant_customer_values` (1:1-Zwilling von `tenant_voice_profile`/018 + project_id + COALESCE-Unique-Aktiv-Index) + `entity_type`-Spalte auf `voice_drift_observation` (für P17). **down_revision='049'** (aktuell höchste echte Migration).
**→ Robert:** (1) Freigabe, die Migration auf Prod/Staging anzuwenden. (2) **Reihenfolge mit #26 klären:** #26 reserviert 050–052, ist aber noch nicht gebaut — wenn #26 vor #43 mergt, muss 053.down_revision auf '052' gebumpt werden (sonst doppelter Alembic-Head). Code (TABLE_MAP/Resolver/Regex) ist mergebar; nur das *Anwenden* der Migration wartet auf dich.

### ~~#46 — Modell-Familienwechsel~~ ✅ ENTSCHIEDEN 2026-06-13 (mistral-small belassen, Switch später; s.u. Erledigt)
### #46 — Modell-Familienwechsel bei 2 von 3 Ex-Bypässen (Qualität validieren)
Umgestellt (US-Calls eliminiert, Compliance gefixt):
- `voice_drift_task` → **S6** (`bedrock/claude-sonnet-4-6@eu-central-1`) = **dasselbe Modell wie zuvor, nur EU-Region** → kein Qualitätsrisiko. ✅
- `md_converter` (MD→JSON) → **S2** (`mistral-small`, EU): Modell-Familienwechsel claude-haiku→mistral. Utility-Call, geringes Risiko.
- `sensitive_detector` (PII-/Sensibilitäts-**Klassifikation**) → **S2** (`mistral-small`, EU): Modell-Familienwechsel. **Qualitätsrelevant** — die Trefferqualität der PII-Erkennung kann sich ändern.
- **→ Robert-Entscheid:** `sensitive_detector` bei mistral-small belassen (günstig) **oder** auf **S6** (Claude-EU, näher am alten Haiku-Verhalten) heben? Empfehlung Architekt: kurzer A/B-Korpuslauf (Knecht) gegen bekannte PII-Beispiele, dann entscheiden. Kein Blocker für den Merge — der US-Leak ist so oder so behoben.

### #36 — routed_to-CHECK-Mini-Migration (nicht blockierend)
Der CHECK-Constraint `telegram_message_log.routed_to` (Migration 019:66) kennt die neuen Targets `p09`/`p13` nicht. Aktuell migrationsfrei auf `'p10'` gemappt (`_ROUTED_TO_MAP`) → Dedupe funktioniert, aber das Log ist semantisch unscharf (p09/p13 erscheinen als p10). **→ Robert: optionale Mini-Migration, die den CHECK um `'p09','p13'` erweitert** (dann Mapping entfernen). Klein, nicht dringend.
Chris-Flags #36: (a) Board 4.6 „optional 2–3 Rückfragen VOR den Aufhängern" wurde als MVP übersprungen (die targeted-Session NACH der Wahl liefert die Rückfragen via Bahn 5) — Lesart bestätigen. (b) Text-Nummern 1/2/3 statt Telegram-Inline-Buttons.

### #24 — Deploy-Pfad (mit Knecht)
SSH Port 10022 vs. self-hosted GitHub-Runner. **→ Richtung entscheiden.**

## ✅ Erledigt / entschieden
- **2026-06-13 #42 Content-Modell:** **Testmodus zuerst.** Gemini-Flash-Lite (S1) bleibt für die
  kreativen Pfade (ideation/questions) während Entwicklung/Test — Ziel ist erst „läuft die ganze Pipeline",
  nicht Qualität. Umstellung auf Quality-Mode (Sonnet-EU/Mistral-Large) erst wenn MVP-Kern zu 100 % steht.
  → Architektur-Folge: **Modell-Modus-Switch** (Testmodus/Produktivmodus/Benutzerdefiniert) in den
  Frontend-Settings, korrekte Modelle je Modus hinterlegt (Issue für späteren Sprint, nicht jetzt).
- **2026-06-13 #43 Migration 053:** **FREIGEGEBEN** zum Anwenden auf Staging/Prod — *nach* Landing von #43
  auf main, mit Alembic-Head-Check (down_revision 049→052 bumpen, falls #26 zuerst landet). Schaltet
  Werte-Trias + #41-Beobachter scharf.
- **2026-06-13 #46 sensitive_detector:** Vorerst auf **mistral-small (S2)** belassen (Testmodus). Absicherung
  ebenfalls über den geplanten Modell-Modus-Switch; A/B-Korpuslauf optional später.

---
*Architekt trägt hier ein, sobald im autonomen Lauf eine Robert-Entscheidung auftaucht. Robert hakt ab oder antwortet inline.*
