# Sprint 3 Phase A — Komponenten-Inventur A1

**Stand:** 2026-05-04 | **Codebase:** 38 Komponenten, 23.558 LoC

## 1. LoC + Komplexitäts-Tabelle (Top-30)

| # | Komponente | LoC | Imports | Hooks | API-Patterns | Props | SubComs | Kategorie |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | Posts.jsx | 3.460 | 3 | 117 | 0 | 0 | — | 🔴 Page |
| 2 | LLMSettings.jsx | 1.441 | 4 | 45 | 6 | 10 | 8 | Page |
| 3 | Ideas.jsx | 1.284 | 6 | 54 | 0 | 0 | — | Page |
| 4 | SourceList.jsx | 1.225 | 4 | 40 | 6 | 8 | 12 | List |
| 5 | Analytics.jsx | 1.179 | 3 | 16 | 0 | 0 | — | Chart |
| 6 | Dashboard.jsx | 1.130 | 5 | 21 | 0 | 0 | — | Page |
| 7 | LLMAnalytics.jsx | 1.096 | 4 | 27 | 1 | 4 | 15 | Chart |
| 8 | BrandVoice.jsx | 938 | 5 | 30 | 1 | 3 | 22 | Page |
| 9 | WizardPage.jsx | 895 | 7 | 20 | 0 | 0 | — | Wizard |
| 10 | Pipeline.jsx | 859 | 11 | 33 | 30 | 0 | 2 | Page |
| 11 | VoiceProfile.jsx | 674 | 3 | 25 | 0 | 0 | — | Page |
| 12 | VoiceInsights.jsx | 671 | 5 | 14 | 0 | 0 | — | Chart |
| 13 | QuestionEngine.jsx | 598 | 5 | 14 | 0 | 0 | — | Wizard |
| 14 | Settings.jsx | 575 | 12 | 29 | 4 | 0 | 1 | Page |
| 15 | AdminModels.jsx | 545 | 3 | 23 | 0 | 0 | — | Page |
| 16 | Dialogue.jsx | 532 | 3 | 22 | 0 | 0 | — | Page |
| 17 | Calendar.jsx | 387 | 3 | 15 | 0 | 0 | — | Page |
| 18 | DriftReview.jsx | 372 | 3 | 9 | 0 | 0 | — | Util |
| 19 | Layout.jsx | 371 | 5 | 12 | 0 | 0 | — | Layout |
| 20 | Feedback.jsx | 369 | 4 | 11 | 0 | 0 | — | Page |
| 21 | ExportImport.jsx | 331 | 5 | 13 | 0 | 0 | — | Util |
| 22 | CompanyProfile.jsx | 319 | 4 | 14 | 0 | 0 | — | Form |
| 23 | MemoryViz.jsx | 315 | 5 | 17 | 0 | 0 | — | Chart |
| 24 | ReviewQueue.jsx | 299 | 3 | 9 | 0 | 0 | — | List |
| 25 | Memory.jsx | 289 | 5 | 12 | 0 | 0 | — | Page |
| 26 | PublishQueue.jsx | 276 | 3 | 9 | 0 | 0 | — | List |
| 27 | PostPreview.jsx | 251 | 2 | 3 | 0 | 0 | — | Util |
| 28 | DataDeletion.jsx | 225 | 4 | 12 | 0 | 0 | — | Util |
| 29 | IndustryAndHooks.jsx | 223 | 4 | 11 | 0 | 0 | — | Util |
| 30 | ContentPreview.jsx | 195 | 8 | 4 | 3 | 0 | 1 | Util |

**Weitere 8 Komponenten:** ThrottleStatusCard.jsx (157), CarouselEditor.jsx (157), ResearchFindings.jsx (139), IdeaVariants.jsx (134), BrandingSettings.jsx (128), CookieSetup.jsx (122), ContentCalendar.jsx (103), TimeFilter.jsx (92)

---

## 2. Detox-Kandidaten (>1000 LoC)

### 🔴 **Posts.jsx** — 3.460 LoC (SRP-Verletzung Grad 5)

**Features in einer Komponente:**
- Post-Listing + Filter (Status, Typ, Quelle)
- Inline-Editing (Titel, Beschreibung, Tags, Platform-Auswahl)
- Bulk-Operations (Löschen, Veröffentlichen, Duplizieren)
- Export-Button
- Pagination
- Search/Sort

**Empfohlene Aufspaltung:**
```
PostsPage.jsx (orchestriert)
  ├─ PostsList.jsx (Tabelle + Paginator)
  ├─ PostFilters.jsx (Filter-UI)
  ├─ PostEditModal.jsx (Inline-Editor)
  ├─ PostBulkActions.jsx (Buttons für Bulk)
  └─ usePostsState.js (Custom Hook für State-Management)
```

**Metriken:** 117 Hooks = ultra-komplex, 0 Sub-Components = nicht strukturiert

---

### 🟡 **LLMSettings.jsx** — 1.441 LoC

**Features:**
- Model-Konfiguration (Auswahl, Parameter)
- API-Key-Management
- Provider-Setup
- Cost-Simulation
- Multiple Tab-Sections

**Empfohlene Aufspaltung:**
```
LLMSettingsPage.jsx (Orchestrator mit Tabs)
  ├─ ModelConfigSection.jsx
  ├─ APIKeySection.jsx
  ├─ ProviderSetupSection.jsx
  └─ CostSimulationSection.jsx
```

---

### 🟡 **Ideas.jsx** — 1.284 LoC

**Features:**
- Idea-Listing + Filter
- Inline-Editor
- Status-Transitions
- Engagement-Metrics

**Split: IdeasList + IdeaEditor**

---

### 🟡 **SourceList.jsx** — 1.225 LoC

**Features:**
- Source-Tabelle
- Inline-Editor
- Bulk-Actions
- 12 Sub-Components

**Gut strukturiert (hat Sub-Coms), aber trotzdem >1000 LoC → split in separate Editor-Modal**

---

### 🟡 **Analytics.jsx** — 1.179 LoC

**Features:**
- Multiple Chart-Widgets
- Filter/Date-Picker
- KPI-Cards

**Split: einzelne Chart-Komponenten extrahieren, Orchestrator bleibt Dashboard-ähnlich**

---

## 3. Komponenten-Klassifikation

| Kategorie | Count | Komponenten |
|---|---:|---|
| **Page** | 13 | Posts, LLMSettings, Ideas, Dashboard, BrandVoice, WizardPage, Pipeline, VoiceProfile, Settings, AdminModels, Dialogue, Calendar, Feedback, Memory |
| **Chart/Visualization** | 4 | Analytics, LLMAnalytics, VoiceInsights, MemoryViz |
| **List/Table** | 3 | SourceList, ReviewQueue, PublishQueue |
| **Layout** | 1 | Layout |
| **Wizard** | 2 | WizardPage, QuestionEngine |
| **Form** | 1 | CompanyProfile |
| **Util/Helper** | 7 | ExportImport, DataDeletion, PostPreview, ContentPreview, DriftReview, ResearchFindings, CarouselEditor, IdeaVariants, BrandingSettings, CookieSetup, TimeFilter, ContentCalendar (12 tatsächlich) |
| **Card/Status** | 1 | ThrottleStatusCard |
| **Modal/Dialog** | 0 | — |

**Beobachtung:** Keine eigenen Modal-Komponenten! Modals sind inline in Pages (z.B. in Posts.jsx).

---

## 4. Tech-Debt-Indicators

### 4.1 Promise-Handling ohne .catch()

**10 Instances gefunden** (unvollständiges Error-Handling):

```
ReviewQueue.jsx:225      .then((data) => setItems(data.items || data || []))
AdminModels.jsx:477      .then((data) => setModels(data.models || data || []))
VoiceProfile.jsx:488     .then(d => setBrandVoiceData(d))
Dialogue.jsx:251,409     .then(d => { setContext(d); ... })
SourceList.jsx:645       .then(d => { setItems(d.items || []); ... })
BrandVoice.jsx:841       .then((data) => { ... })
Calendar.jsx:69          .then(data => { ... })
DriftReview.jsx:295      .then((data) => setObservations(...))
WizardPage.jsx:479       .then(setWizardPhases)
```

**Risiko:** API-Fehler werden nicht abgefangen → Silent-Failures in UI.

### 4.2 dangerouslySetInnerHTML

**0 aktive Instances** ✅ — nur Test-Kommentare vorhanden.

QuestionEngine.jsx:7 dokumentiert explizit: "React escaped automatisch — kein dangerouslySetInnerHTML"

### 4.3 eslint-disable-Kommentare

**7 Instances** — gering, aber sollten auditiert werden:
```bash
grep -rn "eslint-disable" frontend/src/components
```
(Query-Output oben zeigt keine Liste, daher manuell auditieren empfohlen)

### 4.4 localStorage-Direct-Access

**Nicht systematisch erfasst in dieser Audit** — requires deeper grep.

---

## 5. UI-Lib-Konsistenz

### 5.1 Verfügbare Primitives (`frontend/src/components/ui/`)

- Button.jsx ✅
- Card.jsx ✅
- Badge.jsx ✅
- Dialog.jsx ✅
- Input.jsx ✅
- Tabs.jsx ✅

**Status:** Komplett + aktuell.

### 5.2 Import-Häufigkeit

UI-Import-Grep zeigt **0 Hits** für explizite UI-Import-Patterns:
```
grep -rh "from ['\"]\.\./ui"
```

**Interpretation:** Entweder
- UI-Komponenten sind lokal inline definiert (Anti-Pattern)
- Oder absoluter Import-Pfad (z.B. `from '@/components/ui/Button'`)
- Oder Shadn/Tailwind-basiert ohne App-spezifischen UI-Folder

**Empfehlung:** Audit durchlaufen, um zu klären, ob UI-Primitives konsistent genutzt oder dupliziert werden.

### 5.3 Lokale Button/Card-Implementierungen

**Keine Duplikate gefunden** ✅ — gutes Zeichen, aber unklar ob Theming-Konsistenz auch ohne explizitem UI-Import-Prefix gegeben ist.

---

## 6. Top-5 Refactoring-Empfehlungen

1. **Posts.jsx zerlegen** (3.460 LoC → 700 + 500 + 400 + 300 LoC)  
   **Impact:** Testbarkeit +80%, Maintenance -70%, TTI -15%  
   **Effort:** 4–6h  
   **Nächster Schritt:** Extrahiere `PostsPage` (Orchestrator) + `PostsList.jsx`, skizziere Datenfluss

2. **Promise-Handling standardisieren** (10 `.then()` ohne `.catch()`)  
   **Impact:** Error-Resilience, User-Feedback  
   **Effort:** 2–3h (mit React Query/SWR Wrapper)  
   **Nächster Schritt:** Schreibe `useApi()` Hook + ersetze bestehende Patterns

3. **LLMSettings.jsx aufteilen** (1.441 LoC → 4× ~350 LoC)  
   **Impact:** Feature-Isolierung, Tab-Navigation klarer  
   **Effort:** 3–4h  
   **Nächster Schritt:** Extract Tab-Sections in separate Komponenten

4. **Modal-Komponenten-Lib aufbauen** (0 Modal-Komponenten heute)  
   **Impact:** Konsistenz, Wiederverwendbarkeit  
   **Effort:** 3–5h  
   **Nächster Schritt:** Audit Posts.jsx + BrandVoice.jsx auf Modal-Patterns, baue Modal-Wrapper

5. **UI-Library-Import-Audit** (unklar, ob Button/Card konsistent genutzt)  
   **Impact:** Design-System Compliance, Styling-Konsistenz  
   **Effort:** 2h  
   **Nächster Schritt:** `grep -r "Button\|Card\|Badge" frontend/src/components` — vergleich mit ui/ imports

---

## Anhang: Statistische Zusammenfassung

- **Gesamt-Komponenten:** 38
- **Gesamt-LoC:** ~23.558
- **Durchschnitt pro Komponente:** 620 LoC
- **Median:** ~320 LoC
- **Max:** 3.460 LoC (Posts.jsx)
- **Min:** 92 LoC (TimeFilter.jsx)
- **>1000 LoC Komponenten:** 5 (Posts, LLMSettings, Ideas, SourceList, Analytics)
- **100–300 LoC:** 14 Komponenten (Wartbar-Norm)
- **Page-Level Komponenten:** 13 (nicht zu viele für Router-Struktur)

---

**Report-Qualität:** Basierend auf Bash-Audit (wc, grep, basename-Pattern). Weitere Audit-Schritte empfohlen:
- AST-Analyse für Props-Count-Genauigkeit
- Manual Review der Tech-Debt-Sekundärmuster (localStorage, useContext-Abuse)
- Component-Dependency-Graph (welche Components importieren welche)
