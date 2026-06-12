# ROBERT-BACKLOG — Entscheidungen & Freigaben (nur Mensch)

> Hier sammelt der Architekt alles, was **nur Robert** entscheiden/freigeben kann (DB-Migrationen, Provider/Modell-Wechsel, Merges nach main, Firewall/Secrets, Deploy). Der autonome Lauf legt Code dafür vor, **mergt/aktiviert aber nichts** davon selbst. Stand laufend aktualisiert.

## 🔴 Offen — wartet auf Robert

### Merges nach main (kein Selbst-Merge)
- **PR #55** `arch/weekloop` → main: #15 (p08/layer1 LLM-Seam) + #16 (Inbound-Routing) + #43-Konzept + Gesamtreport. Cross-Model-Review GRÜN, 47 Tests lokal grün. **→ review & merge.**
- **PR #53** `knecht/fix-33-json` (P01/P03 JSON-Output) — Knecht, blockiert #32 Eric-E2E. **→ review & merge.**
- **PR #54** `knecht/fix-47-ci-green` (CI main grün). **→ review & merge.**

### #42 — Content-Modell-Entscheid (dringend, betrifft alle kreativen Pfade)
Drei Realitäten: S6 = Sonnet-EU (Bedrock-Frankfurt) · kreative Pfade (ideation/questions) auf Gemini-Flash-Lite remappt · Seam-Bypässe = US-API (wird in #46 behoben).
- **Entscheidung A:** Board sagt „Opus für Content" — bleibt es bei Sonnet-EU als Default (EU-Souveränität schlägt Board-Buchstabe), Opus nur als CONFIRM-Upgrade? **Empfehlung Architekt: ja.**
- **Entscheidung B (dringender):** Der Gemini-Flash-Lite-Remap der kreativen Pfade revidieren (zurück auf ein stärkeres EU-Modell) oder bewusst bestätigen? **Empfehlung: revidieren** — widerspricht dem Board stärker als Sonnet-statt-Opus.

### #43 — Werte-Entität: **neue DB-Tabelle** `tenant_customer_values` (freigabe-robert)
Konzept liegt vor (`docs/CONCEPT-43-werte-entitaet.md`). Implementierung erfordert Alembic-Migration (neue Tabelle + ggf. `entity_type`-Spalte für P17-Drift). **→ Freigabe für DB-Migration + Migrations-Nummern (Kollision mit #26 050–052 prüfen).** Architekt legt Code/Migration vor, wendet sie aber nicht auf Prod an.

### #46 — Modell-Familienwechsel bei 2 von 3 Ex-Bypässen (Qualität validieren)
Umgestellt (US-Calls eliminiert, Compliance gefixt):
- `voice_drift_task` → **S6** (`bedrock/claude-sonnet-4-6@eu-central-1`) = **dasselbe Modell wie zuvor, nur EU-Region** → kein Qualitätsrisiko. ✅
- `md_converter` (MD→JSON) → **S2** (`mistral-small`, EU): Modell-Familienwechsel claude-haiku→mistral. Utility-Call, geringes Risiko.
- `sensitive_detector` (PII-/Sensibilitäts-**Klassifikation**) → **S2** (`mistral-small`, EU): Modell-Familienwechsel. **Qualitätsrelevant** — die Trefferqualität der PII-Erkennung kann sich ändern.
- **→ Robert-Entscheid:** `sensitive_detector` bei mistral-small belassen (günstig) **oder** auf **S6** (Claude-EU, näher am alten Haiku-Verhalten) heben? Empfehlung Architekt: kurzer A/B-Korpuslauf (Knecht) gegen bekannte PII-Beispiele, dann entscheiden. Kein Blocker für den Merge — der US-Leak ist so oder so behoben.

### #24 — Deploy-Pfad (mit Knecht)
SSH Port 10022 vs. self-hosted GitHub-Runner. **→ Richtung entscheiden.**

## ✅ Erledigt / entschieden
- (noch nichts)

---
*Architekt trägt hier ein, sobald im autonomen Lauf eine Robert-Entscheidung auftaucht. Robert hakt ab oder antwortet inline.*
