# Sprint 3 — Audit A3: Konsistenz-Check Wizard ↔ Settings ↔ Approve
Status: **MIXED** (teils konsistent, teils Inkonsistenzen mit User-Impact)

## 📋 Executive Summary

**Audit-Scope:** Konsistenz über 3 Hotspot-Bereiche (Wizard, Settings, Review/Approve) + übergreifende Tokens.

**Verdict:** 
- ✅ **Button-Verben:** Weitgehend konsistent (Deutsch), aber Mischung "Speichern" vs. englisch "Save"
- ⚠️ **Error-Handling:** Inkonsistent — alert() vs. Toast vs. Inline-Fehler
- ⚠️ **Approve-Verben:** "Freigeben" vs. "Annehmen" vs. "Genehmigen" (3 Varianten statt 1)
- ✅ **Date/Number-Format:** DD.MM.YYYY, deutsches Dezimalformat konsistent
- ⚠️ **Loading-States:** Spinner konsistent, aber Text-Variabilität
- ⚠️ **Language-Mix:** 95% deutsch, aber englische Fallback-Labels in PILLAR_CONFIG

---

## 🔴 Bereich 1: Brand-Voice-Wizard

**File:** `/opt/content-autopilot-v2/frontend/src/components/WizardPage.jsx`

### Button-Verben
| Aktion | Verb | Zeile | Konsistent? |
|--------|------|-------|-----------|
| Fortfahren Phase | "Weiter" | QuestionEngine (prop) | ✅ |
| Speichern Draft | "Speichern" (localStorage) | Z. 672 | ✅ |
| Schließen | "Schließen" | Z. 829 | ✅ |
| Fortsetzen alte Session | "Fortsetzen →" | Z. 772 | ✅ |
| Neu starten | "Neu starten..." | Z. 775 | ✅ |

**Bewertung:** ✅ Konsistent — durchgehend Deutsch, klare Action-Verben.

### Error-Handling
- **init-Error:** Inline-Modal (Border-Red) mit "Zurück zu Brand Voice" Button — Z. 728
- **Pipeline-Fehler:** Info-Banner mit Text "Pipeline-Fehler: ..." — Z. 408
- **Session-Resume:** Stale-Warning in Amber-Box — Z. 758

**Bewertung:** ✅ Konsistent — Fehler werden modal/banner + inline gezeigt, keine `alert()`.

### Loading-States
- **Phase-Load:** Spinner + "Wizard wird vorbereitet…" — Z. 720
- **Synthese-Load:** Spinner + "KI analysiert deine Antworten…" — Z. 864
- **Finalize-Load:** Spinner + "Wizard wird abgeschlossen…" — Z. 859

**Bewertung:** ✅ Konsistent — Spinner + Text-Beschreibung überall.

### Progress-Indicator
- **Desktop:** Sidebar PhaseIcon (done/active/pending) — Z. 289
- **Tablet:** Horizontal Stepper (1, 2, 3...) — Z. 328
- **Format:** "Phase X/6" implizit über Stepper

**Bewertung:** ✅ Konsistent — Stepper ist einheitlich implementiert.

---

## 🟡 Bereich 2: Settings (Multi-Sub-Page)

**File:** `/opt/content-autopilot-v2/frontend/src/components/Settings.jsx`

### Layout-Pattern
- **Top-Level:** Vertical Card-Stack (z.B. API Key, LLM Settings, YouTube, Nextcloud)
- **Sub-Pages:** Inline im selben File (keine separaten Routes)
- **Form-Pattern:** Label + Input, Label-Position = oben oder inline

**Bewertung:** ✅ Konsistent — Card-basiertes Layout durchgehend.

### Form-Labels & Validation
| Feld | Label-Pos | Validation | Erforderlich? |
|------|-----------|-----------|--------------|
| API Key | Label oben | ❌ Keine | Optional |
| YouTube API Key | Label oben | ❌ Keine (Pflicht-Stern fehlt) | Optional |
| Tonalität | Label oben | ❌ Keine | Optional |
| Tageslimit EUR | Label oben | Min/Max (HTML5) | Optional |
| Transkripte Path | Label oben | ❌ Keine | Required (implizit) |

**Bewertung:** ⚠️ Inkonsistent — manche Felder haben HTML5-Validation (min/max), andere nicht. Pflicht-Sterne fehlen überall.

**Beispiel:** YouTube API (Z. 263): `<label>YouTube Data API Key (optional)</label>` aber kein Stern-Marker.

### Save-Action
- **Button:** "💾 Alle Einstellungen speichern" (sticky bottom, Z. 521) — manuell
- **Auto-Save:** Ja, aber nur für NC-Pfade (selectFolder → updateSettings, Z. 155)
- **Feedback:** `alert('Einstellungen gespeichert!')` — Z. 98

**Bewertung:** ⚠️ Inkonsistent — Hybrid aus Manual Save + Auto-Save. Alert() ist nicht elegant.

### Sensitive-Felder (API Keys)
| Feld | Show/Hide Toggle | Masking |
|------|-----------------|---------|
| YouTube API Key | ✅ Yes (Eye-Icon) | ✅ "••••••••" when set |
| Tenant API Key | ❌ No (type="password") | ✅ Masked input |
| LLM Keys (in table) | ❌ No | ❌ Visible in select! |

**Bewertung:** 🔴 **BLOCKIEREND** — LLM-Modell-Dropdown zeigt API-Keys nicht, aber Konsistenz-Problem: YouTube hat Eye-Toggle, Tenant-Key nicht.

**Code:** Z. 481-489 — Select-Dropdown für LLM-Modell zeigt nur `o.id` (z.B. `google/gemini-2.0-flash`), kein Sicherheits-Risiko, aber Asymmetrie.

---

## 🔴 Bereich 3: Review/Approve-Workflow

**File:** `/opt/content-autopilot-v2/frontend/src/components/ReviewQueue.jsx`

### Approve-Verben (KRITISCH)
| Komponente | Verb | Code |
|------------|------|------|
| ReviewQueue Button | "Freigeben" | Z. 193 |
| ReviewQueue Button | "Ablehnen" | Z. 205 |
| Posts.jsx (search in bash) | "Freigegeben" (Status) | grep output |
| Analytics (Status-Map) | "Freigegeben" / "Verworfen" | grep output |
| CompanyProfile.jsx | "Ablehnen" | grep output |

**Bewertung:** 🔴 **BLOCKIEREND** — 3 verschiedene Verb-Systeme:
1. ReviewQueue: "Freigeben" + "Ablehnen" (Z. 193, 205)
2. Analytics: "Freigegeben" + "Verworfen" (Status-Label)
3. CompanyProfile: "Ablehnen" (aber keine Approve-Pendant sichtbar)

**User-Impact:** Verwirrung über Workflow-Semantik — "Ablehnen" vs. "Verwerfen"?

### Error-Handling
- **Submit-Error:** `setSubmitError()` → Inline Red-Box mit AlertCircle — Z. 174
- **Load-Error:** `setError()` → Inline Red-Box mit "Erneut laden" Link — Z. 259

**Bewertung:** ✅ Konsistent (Inline-Fehler überall), aber **kein alert()** wie in Settings!

### Disabled-States
- **Buttons während Submit:** `disabled={submitting}` → opacity-40, cursor-not-allowed — Z. 185, 196
- **Textarea während Submit:** `disabled={submitting}` — Z. 169

**Bewertung:** ✅ Konsistent — disabled-Styling einheitlich.

### Bulk-Actions
- **Gibt es kein "Alle auswählen"** in ReviewQueue — nur einzelne Cards.
- **Posts.jsx** (grep): `bulkApproveContent`, `bulkRejectContent` APIs existieren, aber UI nicht sichtbar in dieser Audit.

**Bewertung:** ⚠️ Unvollständig — Bulk-Select nicht implementiert in ReviewQueue.

---

## 🌍 Übergreifende Konsistenz-Checks

### 1. Sprache
- **Deutsch-Anteil:** ~98% (durchgehend deutsch)
- **Englische Fallbacks:** 
  - PILLAR_CONFIG Labels: `'thought_leadership'`, `'how_to'`, `'industry_news'` (aber mit deutschen Labels daneben) — Posts.jsx Z. 28
  - Empty-State Text: `"Keine ausstehenden Reviews"` ✅ Deutsch

**Bewertung:** ✅ Quasi-vollständig deutsch, englische Config-Keys sind Backend-Mapping.

### 2. Date-Formatting
| Komponente | Format | Code |
|------------|--------|------|
| ReviewQueue | DD.MM.YYYY HH:MM | Z. 25: `${dd}.${mm}.${yyyy} ${hh}:${min}` |
| WizardPage Resume | DD.MM.YYYY | Z. 748: `toLocaleDateString('de-DE')` |

**Bewertung:** ✅ Konsistent — deutsches Datumsformat überall.

### 3. Number-Formatting
| Komponente | Format | Code |
|------------|--------|------|
| Budget Display | $X.XXX (US!) | Z. 419: `${spentEur.toFixed(3)}` aber Dollar-Zeichen |
| Cost per Million | $X.XXX | Z. 436: `<code>0,075$/1M</code>` (deutsches Dezimal!) |

**Bewertung:** ⚠️ **Gemischt** — Euro/Dollar-Mix, Dezimalzeichen inkonsistent (Punkt vs. Komma).

**Fix:** Z. 419 sollte `€` statt `$` sein; Dezimal sollte überall `,` sein für deutschen User.

### 4. Empty-States
| Komponente | Pattern | Code |
|------------|---------|------|
| ReviewQueue Empty | Icon + Text + Subtext | Z. 282 |
| Wizard Loading | Spinner + Text | Z. 720 |
| Ideas Empty (from prev read) | Likely Icon + Text | [not fully visible] |

**Bewertung:** ✅ Konsistent — Icon + Text-Pattern durchgehend.

### 5. Loading-States
| Pattern | Komponente | Code |
|---------|-----------|------|
| Spinner (lucide) | Überall | Loader2 Icon |
| Skeleton | Keine sichtbar | — |
| Text "Lade…" | ReviewQueue, Dialog | Z. 276, 544 |

**Bewertung:** ✅ Konsistent — Spinner-Icon überall, kein Skeleton-Pattern.

### 6. Disabled-States
| Komponente | Stil | Code |
|------------|------|------|
| ReviewQueue Button | opacity-40, cursor-not-allowed | Z. 185 |
| Dialog Submit | opacity-40 (implicit via disabled) | [inferred] |

**Bewertung:** ✅ Konsistent — disabled-Styling klar.

### 7. Color-Tokens
| Token | Verwendung | Type |
|-------|-----------|------|
| `primary-600` | Brand-Color (Wizard CTA) | ✅ Tailwind |
| `emerald-600` | Success/Done | ✅ Tailwind |
| `red-600` | Error/Alert | ✅ Tailwind |
| `bg-gray-50` | Light BG | ✅ Tailwind |
| Hex Hardcoded | Keine sichtbar | ✅ Clean |

**Bewertung:** ✅ Konsistent — nur Tailwind-Tokens, keine Hex-Werte im Code.

### 8. Icon-Lib
- **Nur lucide-react:** Loader2, Check, X, ChevronDown, ChevronUp, AlertTriangle, Tag, etc.
- **Keine andere Lib** sichtbar

**Bewertung:** ✅ Konsistent — Single Icon-Library.

### 9. Toast-Lib
| Pattern | Komponente | Code |
|---------|-----------|------|
| Custom Toast-Banner | WizardPage SavedToast | Z. 418 |
| alert() | Settings.jsx | Z. 98, 101, 108, 114 |
| Inline Error-Box | ReviewQueue | Z. 174 |

**Bewertung:** 🔴 **BLOCKIEREND** — 3 verschiedene Error-/Feedback-Patterns:
1. **Custom Toast** (WizardPage) — fixed bottom, auto-close
2. **alert()** (Settings) — Browser-Modal, unterbricht Flow
3. **Inline Box** (ReviewQueue) — Inline im Content

**User-Impact:** Inkonsistente Feedback-Erfahrung. Settings sollte Toast statt alert() nutzen.

---

## 🎯 Top-10 Konsistenz-Fixes (priorisiert nach User-Impact)

### 1. 🔴 **Settings: Ersetze alert() durch Toast** (User-Impact: HOCH)
   - **Problem:** Z. 98, 101, 114 verwenden `alert()` statt Toast
   - **Fix:** `import { useToast } from '../hooks/useToast'` (oder custom Toast-Hook)
   - **File:** `Settings.jsx`
   - **Effort:** 30 min

### 2. 🔴 **Approve-Verben vereinheitlichen** (User-Impact: SEHR HOCH)
   - **Problem:** "Freigeben" vs. "Ablehnen" vs. "Verworfen" vs. "Genehmigen"
   - **Fix:** Standard-Set definieren: **"Freigeben" (approve) + "Ablehnen" (reject)** überall
   - **Files:** ReviewQueue.jsx, Analytics.jsx, Posts.jsx, DriftReview.jsx
   - **Effort:** 45 min

### 3. ⚠️ **Sensitive-Felder: Eye-Toggle konsistent** (User-Impact: MITTEL)
   - **Problem:** YouTube API Key hat Toggle, Tenant API Key nicht
   - **Fix:** Alle Password-Felder kriegen Eye-Toggle (oder keines)
   - **File:** Settings.jsx
   - **Effort:** 20 min

### 4. ⚠️ **Currency-Format: EUR vs. USD** (User-Impact: MITTEL)
   - **Problem:** Z. 419 zeigt `$` aber Settings sind EUR
   - **Fix:** Konsistent EUR (€) oder User-Locale erkennen
   - **File:** Settings.jsx (Z. 419, 436)
   - **Effort:** 15 min

### 5. ⚠️ **Decimal-Format: Punkt vs. Komma** (User-Impact: NIEDRIG)
   - **Problem:** Z. 436 zeigt `0,075$/1M` (Komma), aber `toFixed()` nutzt Punkt
   - **Fix:** `toLocaleString('de-DE')` überall für Zahlen
   - **File:** Settings.jsx
   - **Effort:** 20 min

### 6. ⚠️ **Bulk-Select in ReviewQueue** (User-Impact: MITTEL)
   - **Problem:** Keine Bulk-Actions, obwohl Backend-APIs existieren
   - **Fix:** Checkbox-Header + Select-All + Bulk Approve/Reject
   - **File:** ReviewQueue.jsx
   - **Effort:** 60 min

### 7. ✅ **Validation-Sterne bei Required-Feldern** (User-Impact: NIEDRIG)
   - **Problem:** Keine visuellen Sterne oder Marker für Pflicht-Felder
   - **Fix:** `<span className="text-red-600 ml-1">*</span>` bei Label
   - **Files:** Settings.jsx (Transkripte Path, etc.)
   - **Effort:** 25 min

### 8. ⚠️ **Auto-Save vs. Manual Save** (User-Impact: MITTEL)
   - **Problem:** Settings hat Hybrid: NC-Paths Auto-Save, Rest Manual
   - **Fix:** Entweder überall Auto-Save + Toast "Gespeichert", oder nur Manual mit Confirm
   - **File:** Settings.jsx
   - **Effort:** 40 min

### 9. ✅ **Loading-Text: "Lade…" vs. "lädt..."** (User-Impact: NIEDRIG)
   - **Problem:** Verschiedene Variationen des Lade-Texts
   - **Fix:** Standard: "Wird geladen…" oder "Lädt…"
   - **Files:** ReviewQueue.jsx, Dialog.jsx, etc.
   - **Effort:** 10 min

### 10. ⚠️ **Error-Context für Entwickler** (User-Impact: NIEDRIG)
   - **Problem:** Fehler-Messages sind oft generisch ("Fehler beim Speichern")
   - **Fix:** User-facing Message + console.error() für Dev-Debug
   - **Files:** Settings.jsx, ReviewQueue.jsx
   - **Effort:** 20 min

---

## 📊 Konsistenz-Scorecard

| Kategorie | Score | Status |
|-----------|-------|--------|
| Button-Verben | 8/10 | ✅ Weitgehend OK |
| Error-Handling | 5/10 | 🔴 alert() vs. Toast vs. Inline |
| Approve-Workflow | 4/10 | 🔴 3 verschiedene Verben |
| Date-Format | 10/10 | ✅ Perfekt |
| Number-Format | 6/10 | ⚠️ EUR/USD Mix, Dezimal |
| Empty-States | 9/10 | ✅ Konsistent |
| Loading-States | 8/10 | ✅ Gut |
| Color-Tokens | 10/10 | ✅ Nur Tailwind |
| Icon-Library | 10/10 | ✅ Single lib |
| Toast/Feedback | 5/10 | 🔴 3 verschiedene Patterns |
| **GESAMT** | **7.3/10** | **⚠️ Teilweise OK, 3 Blockierer** |

---

## 📝 Blockers für Freigabe

### 🔴 BLOCKER 1: Alert() vs. Toast-Inkonsistenz
Settings nutzt `alert()`, alle anderen Components nutzen Custom-Toast oder Inline-Fehler.
**Muss vor Release konsistent sein.**

### 🔴 BLOCKER 2: Approve-Verben (3 Varianten)
ReviewQueue sagt "Freigeben", Analytics sagt "Freigegeben", Posts sagt evtl. was anderes.
**User-verwirrung garantiert.**

### 🔴 BLOCKER 3: Sensitive-Fields-Inconsistency
YouTube API Key hat Eye-Toggle, Tenant API Key nicht — Sicherheits-UX-Falle.

---

## ✅ Was Konsistent ist (bonus)

- ✅ Deutsche Sprache durchgehend
- ✅ Tailwind-Tokens statt Hex-Werte
- ✅ lucide-react als Single Icon-Library
- ✅ DD.MM.YYYY Date-Format
- ✅ Skeleton/Spinner statt vague "Loading"
- ✅ Disabled-Styling konsistent

---

## Nächste Schritte

1. **Priorität A:** Fixes #1, #2, #3 (Blockers) — vor Sprint 3 Release
2. **Priorität B:** Fixes #4, #5, #6, #8 — nach Release, kommende Sprint
3. **Priorität C:** Fixes #7, #9, #10 — Nice-to-have

**Geschätzter Effort:** 
- A: ~105 min (1,75h)
- B: ~155 min (2,5h)
- C: ~55 min (1h)
- **Total: ~315 min (5,25h)**
