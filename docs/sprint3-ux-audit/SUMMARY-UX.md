# Sprint 3 — UX-Audit Synthese (Phase B)

**Datum:** 2026-05-05
**Methode:** 4 parallele Explorer-Subagents, Code-Inspektion ohne Browser. Detail-Reports unter A1/A2/A3/A4.
**Input:** 38 JSX-Komponenten, 23 558 LoC, 14 Routes, 18 Sidebar-Items, 211 API-Endpoints.

---

## Pro-Audit-Status

| Audit | Status | Kern-Aussage |
|---|---|---|
| A1 Komponenten-Inventur | 🟡 | Posts.jsx 3 460 LoC + 117 Hooks ist SRP-Bruch Grad 5; 4 weitere Files >1 000 LoC; 0 Modal-Komponenten-Lib; 10× Promise ohne `.catch` |
| A2 User-Journey | 🟡 | 12 Friction-Punkte für Eric, Anna kämpft mit Cognitive Overload, Robert hat 2 Blocker (kein Audit-Trail-UI, kein Canary-UI) |
| A3 Konsistenz | 🟡 | 3 Blocker (alert() vs Toast, Approve-Verb-Mix, Sensitive-Field-Asymmetrie); ansonsten Sprache + Date-Format + Tailwind-Tokens konsistent |
| A4 Mobile | 🟡 | 60% Touch-Target-Coverage; Heatmap-Zellen 6×6 px (Demo-Blocker); Sidebar-Responsive-Strategie unklar |

---

## Top-3 pro Persona

### Eric (Tenant-Admin, erstes Login)
1. 🔴 **Keine Step-by-Step-Roadmap nach Wizard-Finalize** (`WizardPage.jsx:13`) — User sitzt verloren da, keine "Nächste 3 Schritte"-Modal.
2. 🟡 **Wizard-Phase 3 mit 9 Fragen zu lang** (`WizardPage.jsx:85-138`) — Session-Abbruch-Risiko, keine Pause-Funktion, keine optional-skip-Hinweise.
3. 🟡 **Brand-Voice-Säulen-Pflicht unklar** (`BrandVoice.jsx`) — drei Profile (voice/customer/avatar) ohne sichtbares "X/3"-Progress, Eric merkt erst nach Versuch dass alle 3 nötig sind.

### Anna (Daily Driver)
1. 🔴 **Cognitive Overload durch 18 Sidebar-Items** (`Layout.jsx:29-56`) — Core-Actions (Idee→Post→Schedule) über 3-4 Pages verteilt, keine "Heute"-Ansicht.
2. 🟡 **Loading-States sind Text statt Spinner** (`Ideas.jsx:42` "Lade Fragen...", `WizardPage.jsx` Synthesis ohne Feedback) — wirkt wie Freeze.
3. 🟡 **Post-Freigeben + Einplanen sind 2 Klicks** — Anna will "Freigeben & Mittwoch 09:00 schedulen" als ein Modal.

### Robert (Reviewer / QA)
1. 🔴 **Keine Audit-Trail-UI für DSGVO-Compliance** — Robert muss SSH + psql, um `llm_call_logs`, `deletion_requests`, `throttle_events` einzusehen. Kein Self-Service.
2. 🔴 **Kein Model-Rollout-UI für Canary-Deploy** — `AdminModels.jsx` deckt nur Backtest, Canary aus `#150` ist nur als Celery-Task. Kein UI mit %-Slider + Recall-Diff + Rollback-Button.
3. 🟡 **Runaway-Heatmap zu granular, nicht actionable** (`LLMAnalytics.jsx:622`) — 7×24=168 Zellen mit 6 px sind weder Touch-fähig noch klickbar für Drill-Down.

---

## Severity-Liste konsolidiert

### 🔴 Blocker (vor Demo Eric/Christoph fixen, Sprint 3C)

| # | Was | File:Line | Persona | Aufwand |
|---|---|---|---|---|
| B1 | Heatmap-Zellen 6×6 px → mind. 32 px | `LLMAnalytics.jsx:622` | Robert/Mobile | S |
| B2 | "alert()" in Settings → Toast-System | `Settings.jsx:98, 245` | Alle | S |
| B3 | Audit-Trail-UI (`/admin/audit-logs` neu) | — | Robert | L |
| B4 | Canary-Rollout-UI (`/admin/models/rollout` neu) | — | Robert | L |
| B5 | Approve-Verben vereinheitlichen ("Freigeben") | div. Files | Alle | S |
| B6 | Posts.jsx 3 460 LoC zerlegen (5 Sub-Komponenten) | `Posts.jsx` | Wartbarkeit | L |

### 🟡 Friction (Sprint 3C / 3D)

| # | Was | File:Line | Aufwand |
|---|---|---|---|
| F1 | Loading-Spinner statt Text | `Ideas.jsx:42`, `WizardPage.jsx` | S |
| F2 | Breadcrumb-Navigation in Layout | `Layout.jsx` | M |
| F3 | Sidebar-Items gruppieren (Workflow vs Konfig) | `Layout.jsx:29-56` | M |
| F4 | "Nächste Schritte"-Modal nach Wizard-Finalize | `WizardPage.jsx:13` | S |
| F5 | "Freigeben & Einplanen" Single-Modal | `Posts.jsx`, `Calendar.jsx` | M |
| F6 | Quick-Generate-Card auf Dashboard | `Dashboard.jsx` | S |
| F7 | Wizard-Phase 3 auf max 5 Fragen reduzieren | `WizardPage.jsx:85-138` | M |
| F8 | Pflicht-Sterne in Settings-Forms | `Settings.jsx` | S |
| F9 | Sensitive-Felder-Show/Hide konsistent | `Settings.jsx`, `LLMSettings.jsx` | S |
| F10 | Promise-Handling standardisieren (`useApi`-Hook) | 10 Files | M |

### 🔵 Polish (Sprint 4+)

| # | Was | Aufwand |
|---|---|---|
| P1 | Modal-Komponenten-Lib aufbauen (Posts, NCPicker, AddProvider extrahieren) | M |
| P2 | LLMSettings 1 441 LoC in 4 Section-Files splitten | M |
| P3 | Mobile-responsive Sidebar (Hamburger/Drawer < 640 px) | M |
| P4 | `text-xs` (10 px) auf mobile via `text-clamp()` skalieren | S |
| P5 | UI-Lib-Import-Audit (lokale vs `ui/`-Imports) | S |

---

## Re-Design-Vorschläge je Hotspot

### Hotspot 1 — Sidebar-Information-Architecture

**Aktuell:** 12 Main + 5 BrandVoice + 1 Admin = 18 unstrukturierte Items.

**Vorschlag:** 3 Gruppen + Mobile-Drawer

```
┌─ ARBEITSABLAUF ──────────  (Daily Driver = Anna)
│  Dashboard
│  Ideen
│  Posts
│  Kalender
│
├─ INHALTE ─────────────────  (Setup = Eric)
│  Quellen
│  Brand Voice ▾
│   ├─ Wizard
│   ├─ So liest KI mich
│   └─ Review-Queue
│  Memory ▾
│   ├─ Liste
│   └─ Karte
│
├─ ANALYSE & ADMIN ─────────  (QA = Robert)
│  Analytics
│  LLM-Kosten
│  Audit-Logs ★ NEU
│  Models / Rollout ★ NEU
│  Einstellungen
│  Feedback
└─
```

Auf < 640 px: Hamburger-Drawer mit gleicher Struktur.

### Hotspot 2 — Onboarding-Flow für Eric

**Aktuell:** Dashboard → Brand Voice → Upload? Wizard? → Ende ohne Roadmap.

**Vorschlag:** Stepper + "Nächste Schritte"-Modal

```
[Dashboard]
   │ Erst-Login: Onboarding-Banner
   ▼
[Step 1] Brand-Voice einrichten
   │ Banner: "Wizard starten" (1 CTA, kein 3-Profile-Karten-Confusing)
   ▼
[Wizard 6 Phasen]
   │ Phase 3: max 5 Fragen, "Mehr Fragen anzeigen ▾" für die anderen 4
   │ Auto-Save lokal alle 30s
   ▼
[Synthese-Loading]
   │ Spinner + "KI analysiert deine Antworten — ca. 90 Sekunden"
   ▼
[Erfolg-Modal: "Nächste 3 Schritte"]
   │ ① Quellen anlegen (RSS/YouTube/Telegram-Voice)
   │ ② Idee picken
   │ ③ Post freigeben
   │ Buttons "Schritt 1 starten" + "Später"
```

### Hotspot 3 — Robert-Admin-Cockpit

**Aktuell:** Robert macht alles via SSH + psql. Audit-Trail ist DB-only, Canary ist Celery-only.

**Vorschlag:** 2 neue Pages

**`/admin/audit-logs`** — neuer Tab unter Admin-Section
- Filter: Tenant, Date-Range, Aktion (`llm_call`, `deletion_request`, `throttle_event`, `cache_hit_alert`, `model_view`)
- Tabelle mit Pagination + CSV-Export
- Detail-Drawer pro Row: Wer/Was/Wann/Status

**`/admin/models/rollout`** — neuer Tab parallel zu `models/backtest`
- Liste Embedding-Modelle (`gemini-embedding-001-1536d`, etc.) mit Tenant-%-Slider
- Recall-Diff vs Baseline (live aus `drift_monitor_task`)
- Rollback-Button (1-Klick → setzt Tenant-Subset zurück auf vorheriges Modell)

### Hotspot 4 — Posts.jsx-Detox

3 460 LoC + 117 Hooks → Refactor zu 5 Sub-Komponenten:

```
PostsPage.jsx (Orchestrator, ~400 LoC)
├─ PostsList.jsx (Tabelle + Pagination, ~600 LoC)
├─ PostFilters.jsx (Status/Typ/Quelle, ~200 LoC)
├─ PostEditModal.jsx (Inline-Editor, ~700 LoC)
├─ PostBulkActions.jsx (Buttons, ~200 LoC)
└─ usePostsState.js (Custom-Hook für State, ~300 LoC)
```

Bonus: gleichzeitig Modal-Komponenten-Lib aufbauen (Polish P1).

### Hotspot 5 — Loading + Error-Standards

**Aktuell:** Mix aus `alert()`, Inline-Errors, Toast, Text-Loading.

**Vorschlag:** zwei Hooks + ein Toast-System

- `useApi(asyncFn, deps)` — wraps async, gibt `{data, loading, error, retry}`. Catch eingebaut, kein silent-failure.
- `useToast()` — replaces `alert()`. Variants: `success`, `error`, `info`, `warning`. Default Position bottom-right, Mobile bottom-center, max 3 stacked.
- Lade-Convention: bei loading `<Loader2 className="animate-spin" />` + `<span>Lade…</span>`. Bei `loading > 1s`: skeleton.

---

## Phase-C-Plan (Top-3 pro Persona, "kein Big-Bang")

Das META-PLAN-Mantra "Top-3 pro Persona, kein Big-Bang" → konkret:

### Eric (Onboarding)
- C-Eric-1 **Wizard-Phase-3 reduzieren** auf 5 Pflicht + "Mehr Fragen ▾"
- C-Eric-2 **"Nächste Schritte"-Modal** nach Wizard-Finalize mit 3 CTAs
- C-Eric-3 **Brand-Voice-Säulen-Progress** (X/3) sichtbar machen + 1-CTA-Banner

### Anna (Daily Driver)
- C-Anna-1 **Sidebar-Reorg** in 3 Gruppen + Mobile-Drawer
- C-Anna-2 **Loading-Spinner-Standard** überall (Ideas/Wizard/Quick-Generate)
- C-Anna-3 **"Freigeben & Einplanen"-Single-Modal** (1 Klick statt 2)

### Robert (Reviewer)
- C-Robert-1 **`/admin/audit-logs`-Page** (Filter + CSV-Export + Detail-Drawer)
- C-Robert-2 **`/admin/models/rollout`-Page** (%-Slider + Recall-Diff + Rollback)
- C-Robert-3 **Heatmap-Zellen 6→32 px** + Click-to-Drilldown ("Top Queries in Stunde XY")

**Quer-schneidend (alle Personas):**
- C-Cross-1 **Toast-System** (`useToast()` + alert()-Replacements)
- C-Cross-2 **Posts.jsx-Detox** (5 Sub-Komponenten)
- C-Cross-3 **Approve-Verb-Vereinheitlichung** ("Freigeben" überall)

---

## Aufwand-Schätzung Phase C

| Bereich | S | M | L |
|---|---|---|---|
| Eric | 2 (C-1 nach Reduzierung trivial, C-3 ein Banner) | 1 (C-2 Modal mit 3 CTAs) | — |
| Anna | 1 (C-2 Spinner) | 2 (C-1 Sidebar, C-3 Single-Modal) | — |
| Robert | — | 1 (C-3 Heatmap-Click) | 2 (C-1 Audit, C-2 Canary — neue Pages) |
| Cross | 1 (C-3 Verben) | 1 (C-1 Toast) | 1 (C-2 Posts-Detox) |
| **Total** | **4 S** | **5 M** | **3 L** |

S = ≤ 1 Tag, M = 1-3 Tage, L = ≥ 1 Woche.

**Realistisch:** Sprint 3C kann alle S + 2-3 M abarbeiten. L-Items in Sprint 4 verschieben (passt zur META-PLAN-Sequenz: Sprint 4 = Security-Härtung, da kann Audit-Trail-UI + Canary-UI gleich rein).

---

## Methodik-Hinweise

- Browser-Use CLI nicht verfügbar — alle Findings via Code-Inspektion (file:line-Belege).
- Mobile-Verifikation an echtem Device (iPhone SE 375×812) **muss Robert/Louis manuell machen**, bevor Sprint 3C startet.
- Phase C wird **nicht hier** gestartet — Robert ist Gate, entscheidet welche der 12 C-Items in den nächsten Sprint.

---

## Acceptance-Status für Sprint 3 Phase A+B

- [x] A1 Komponenten-Inventur (`A1_komponenten_inventur.md`, 263 Zeilen)
- [x] A2 User-Journey-Audit (`A2_user_journey.md`, 232 Zeilen)
- [x] A3 Konsistenz-Check (`A3_konsistenz_check.md`, 346 Zeilen)
- [x] A4 Mobile-Audit (`A4_mobile_audit.md`, 172 Zeilen)
- [x] **SUMMARY-UX.md** (dieser File) mit Severity-Liste + Top-3 pro Persona + Phase-C-Plan
- [ ] Mobile-Verifikation am echten Device (Robert/Louis)
- [ ] Robert reviewt + entscheidet welche C-Items als Issues angelegt werden
