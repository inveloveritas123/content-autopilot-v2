# Sprint 3 Phase A — UX-Audit: User-Journey für 3 Personas

## Executive Summary

Analyse der User-Journeys für 3 Personas durch die Content-Autopilot-UI (frontend/src): Tenant-Admin (Onboarding), Tenant-User (Daily Driver), Reviewer (QA/Robert). Code-basierte Audit ohne Browser-Nutzung — Findings via statische Code-Analyse (App.jsx, Layout.jsx, Dashboard.jsx, WizardPage.jsx, BrandVoice.jsx, Posts.jsx, Ideas.jsx, LLMAnalytics.jsx).

**Top-3 Cross-Persona Schmerzen:**
1. 🔴 **Fehlende Breadcrumb-Navigation** — User können sich verlaufen, keine klare "wo bin ich"-Orientierung
2. 🟡 **Loading-States nicht überall** — Wizard/Post-Generierung: keine Spinner/Skelette sichtbar (Dashboard.jsx, WizardPage.jsx)
3. 🟡 **Viel zu viele Sidebar-Items** (12 Main + 5 BrandVoice + 1 Admin) — CTA-Überflutung, Tab-Mentalität statt hierarchisch

---

## Persona 1: Eric — Tenant-Admin (Erstes Login)

**Goal:** "Ich bin neuer Tenant. Ich will Brand-Voice einrichten und meinen ersten Post veröffentlichen."

### Journey-Tabelle

| Schritt | Was sieht Eric | Was tut er | Friction (Severity) |
|---------|---|---|---|
| 1. Login | Landing auf `/` (Dashboard) — Setup-Checkliste prominently angezeigt (Zeile 689–806 Dashboard.jsx) | Liest Checkliste: "Brand Voice einrichten" (urgent=amber) | 🔵 Klar, aber 4er-Grid kann klein wirken auf Mobile |
| 2. Navigation zu Brand Voice | Setup-Checkliste hat Button "Brand Voice einrichten →" mit ActionLabel (Zeile 718) | Klickt den Button → leitet zu `/brand-voice` | 🔵 Explizit, ok |
| 3. BrandVoice-Seite | BrandVoice.jsx zeigt 3 Profil-Upload-Optionen (voice_profile, customer_context, audience_avatar) — je mit Icon (Zeile 58–77) | Sieht "Brand Voice Profil", "Kundenkontext", "Zielgruppen-Avatar" — weiß nicht welcher Reihenfolge oder ob alle Pflicht sind | 🟡 **Fehlende Hierarchie** — sind alle 3 Pflicht oder optional? Keine Reihenfolge-Guidance |
| 4. Datei-Upload | ColumnSelectModal öffnet (Zeile 79–134), Benutzer wählt einen Typ | Kann File uploaden oder aus NextCloud importieren | 🔵 Zwei Wege ok, aber Defaults könnten helfen |
| 5. Wizard starten | BrandVoice.jsx hat Link zu `/brand-voice/wizard` (Zeile 39 App.jsx) | Klickt "Wizard starten" oder wird nach Upload gefragt | 🟡 **Unklar wann Wizard startet** — nach Upload? Oder separater Schritt? |
| 6. Wizard Phase 1 | WizardPage.jsx renderiert WIZARD_PHASES[0] (Zeile 20–50): "Ankommen & Geschichte" mit 3 Fragen | Eric sieht lange offene Textfelder (q1_1, q1_2, q1_3) ohne erwartete Antwort-Länge | 🔴 **Keine Längen-Hints** — Eric tippt 2 Sätze, könnte viel mehr sein nötig |
| 7. Wizard Phasen 2–4 | 4 Phasen insgesamt (Zeile 20–174 WizardPage.jsx): Ankommen, Alltag, Zielkunde, Angebot. Phase 3 hat 9 Fragen (!) | Eric navigiert durch mit "Nächste Phase" / "Zurück" (vermutete UX, Code zeigt PHASES-Array) | 🟡 **Phase 3 mit 9 Fragen sehr lang** — kein Zwischenspeichern sichtbar, könnte Session-Abbruch-Risiko sein |
| 8. Synthesis + Finalisierung | Nach Phase 4: `finalizeWizardSession()` wird aufgerufen (Zeile 13 WizardPage.jsx) | System generiert Brand-Voice-Profil (KI-Synthesis) — sollte 1–2 Min dauern | 🟡 **Kein Loading-Dialog sichtbar** — keine Rückmeldung dass KI arbeitet, Eric wartet eventuell verwirrt |
| 9. Nach Wizard: Wo lande ich? | Nach finalizeWizardSession() — Navigation unklar, vermutlich zurück zu `/brand-voice` | Eric sieht sein neuer Brand-Voice-Profil oder wird gefragt, was nächstes ist | 🟡 **Keine "Nächste Schritte" Anleitung** — Eric weiß nicht: Jetzt Quellen adden? Jetzt Posts erstellen? |
| 10. Erste Idee generieren | Dashboard zeigt "Inhaltsquellen hinzufügen" (Checkliste Step 2) als nächstes | Eric muss Sources adden bevor Ideen kommen | 🔵 Das ist logisch, Checkliste führt ihn |
| 11. Erste Post generieren | Eric navigiert zu `/ideas`, sieht leere Liste oder generierte Ideas | Klickt eine Idee → `InlineQA` (Ideas.jsx Zeile 42–122) zeigt "Fragen beantworten" oder "⚡ Quick Post" (Zeile 112) | 🔵 Quick-Post-Button sichtbar, aber nicht-erzogen warum man Q&A überspringen sollte |
| 12. First Post publizieren | Eric geht zu `/posts` (Dashboard Zeile 813) — sieht seine Draft-Posts | Klickt Post → kann editieren, dann "Freigeben" + "Einplanen" (vermutete UX) | 🟡 **Zwei separate Klicks nötig** (Freigeben, dann Einplanen) — könnte 1-Klick sein ("Freigeben & Einplanen") |

### Top-3 Pain-Points für Eric

1. **🔴 Fehlende Step-by-Step Guidance nach Brand Voice Wizard**
   - Nach Finalisierung: keine Roadmap zur "Ersten Post"-Veröffentlichung
   - Location: WizardPage.jsx Zeile 13 (finalizeWizardSession), dann?
   - Empfehlung: Modal mit "Nächste 3 Schritte" anzeigen

2. **🟡 Wizard Phase 3 mit 9 Fragen überfordert**
   - Q3_1 bis Q3_9 (Zeile 85–138) sind tiefe offene Fragen
   - Kein Zwischenspeichern, kein Estimator "9 von 9 Fragen", keine Pause-Funktion
   - Empfehlung: Max 5 Fragen pro Phase, optionale "Überspringen mit Default" für Q3_9 (Kundenquotes)

3. **🟡 Unklar ob Brand-Voice 3-teilig oder kann Subsets machen**
   - 3 Profil-Typen (voice_profile, customer_context, audience_avatar) — alle Pflicht?
   - Code: BrandVoice.jsx und Dashboard.jsx (Zeile 691–696) zeigen: "bvPillarsCount === 3" muss alle sein
   - UX-Problem: Erst nach Versuch merkt Eric dass 3 Pflicht sind
   - Empfehlung: Badge "3/3 Säulen" auf BrandVoice-Seite, oder "Nur 2 nötig zum Starten" wenn nur 2 gemacht

---

## Persona 2: Anna — Tenant-User (Daily Driver)

**Goal:** "Ich bin schon onboarded. Ich will heute schnell einen Post zum Thema X generieren."

### Journey-Tabelle

| Schritt | Was sieht Anna | Was tut sie | Friction (Severity) |
|---------|---|---|---|
| 1. Login → Dashboard | Dashboard.jsx zeigt KPI-Grid (6 Cards), Setup-Checkliste, Today's Brief, Week Schedule, Pipeline Bar, usw. | Anna sucht "Post erstellen" oder "Idee generieren" — Layout hat 12 Sidebar Items + 5 Sub-Items | 🔴 **Zu viele Clicks bis zu Core-Action** — `/posts` vs `/ideas` vs `/pipeline` — nicht klar welche zuerst |
| 2. Schnelle Idee pumpen | Dashboard hat "Auto-Pipeline" Button (Zeile 661–669) — triggert `triggerAutoPipeline()` | Anna klickt Button — Text sagt "Analysieren + Generieren + Ideation" aber unklar was davon sie gerade braucht | 🟡 **Button-Label zu technisch** — sollte "Neue Ideen generieren" heißen |
| 3. Manuelle Idee erstellen | Dashboard zeigt neueste Ideen unten (Zeile 990–1029) — 6 Ideen in List | Wenn Anna schnell eine Idee will: muss zu `/ideas` gehen und dort Manuelles erstellen (Ideas.jsx, Zeile 4: `createManualIdea` API) — aber kein "Neue Idee"-Button auf Dashboard sichtbar | 🟡 **Manuell Idee erstellen nicht von Dashboard zugänglich** — 1 Click zu viel |
| 4. Idee auswählen & detaillieren | Ideas.jsx zeigt Liste mit Status-Badge (Neu, Fragen offen, Beantwortet, Post da) — jede Idee expandierbar | Anna klickt Idee → `InlineQA` Modal öffnet (Zeile 42–122) | 🔵 Expandierbar ist ok |
| 5. Quick-Generate ohne Q&A | Wenn Idee noch nicht beantwortet: "⚡ Quick Post (ohne Q&A)" Button (Zeile 108–113) — triggert `quickGeneratePost()` | Anna klickt → Post generiert in ~30 Sekunden, ABER: Zeile 42 sagt "Lade Fragen..." wenn idea falsy | 🟡 **Loading-State ist nur Spinner-Text "Lade Fragen..."** — kein Skeleton/Spinner-Icon, könnte wie freeze wirken |
| 6. Post ansehen & editieren | Post wird unter `/posts` gerendert (Posts.jsx, Zeile 1–200+) — zeigt Post-Text in Textarea | Anna sieht Post, kann mit FormatToolbar (Zeile 192–200+) formatieren (Bold, Italic, etc.) | 🔵 Format-Toolbar ok |
| 7. Post-Quality-Check | Posts.jsx `postScore()` (Zeile 129–171) berechnet Score A–D basiert auf Länge, Hook, Absätze, Emojis, CTA | Anna sieht Grade + 3 Tips (Zeile 164–170) — z.B. "Hook ohne Frage — Fragen steigern Kommentare" | 🔵 Smart und umsetzbar |
| 8. Hashtags hinzufügen | Posts.jsx hat SHK_HASHTAGS (Zeile 36–57) — statische Kategorien (Fachgebiet, Energiewende, Unternehmer, Reichweite) | Anna kann Hashtags copy-pasten oder API `suggestHashtags()` nutzen (Zeile 3) — aber UI nicht sichtbar in Code-Ausschnitt | 🟡 **Hashtag-Suggestion-UI nicht in gelesenen Zeilen** — vermutlich unter Post-Details versteckt |
| 9. Schedule Post | Dashboard WeekScheduleWidget (Zeile 312–423) zeigt diese Woche mit Lücken | Anna kann hier oder unter `/calendar` einen Post einplanen — Button "Kalender" sichtbar (Zeile 369) | 🔵 Calendar-Link ok |
| 10. Finales Freigeben | Anna klickt "Freigeben" (vermutete UX) — Post wird `approveContent()` (Zeile 3) | Status ändert zu "Freigegeben" | 🔵 Unklar aber vermutlich ok |
| 11. Performance tracken | Nach 2 Std: Anna will wissen wie Post performat → Dashboard zeigt "Trending Keywords" (Zeile 1087–1109) aber kein Post-spezifisches Tracking sichtbar | Müsste zu `/analytics` gehen oder auf LinkedIn direkt schauen | 🟡 **Keine Post-spezifischen Real-Time-Stats im Feed** — nur aggregiert unter Analytics |

### Top-3 Pain-Points für Anna

1. **🔴 Zu viele Sidebar-Navigationspunkte — Cognitive Overload**
   - 12 Main Items + 5 BrandVoice + 1 Admin = 18 Clicks zur gleichen Daten
   - Die Core-Actions (Post erstellen, Idee ansehen, Schedule) sind über 3–4 unterschiedliche Seiten verteilt (`/ideas`, `/posts`, `/calendar`)
   - Empfehlung: Erstelle "Quick-Generate" Card auf Dashboard mit Idee + Post in einem Flow, oder "Heute"-Tab mit Daily-Arbeitsablauf

2. **🟡 Loading & Status-Feedback: Spinners sind Text, nicht Icons**
   - Ideas.jsx Zeile 42: "Lade Fragen..." ist als `<div>` Text ohne Loader-Icon
   - WizardPage.jsx Zeile 8: Hat Loader2-Icon importiert, aber Nutzung im Wizard-Code nicht vollständig lesbar
   - Anna wartet auf Quick-Post und sieht nichts bewegen → fühlt sich wie Freeze
   - Empfehlung: `<Loader2 className="animate-spin" />` für alle Async-Operationen > 500ms

3. **🟡 Post-Freigeben + Einplanen sind zwei Schritte, sollten eins sein**
   - Zeile 813 (Dashboard): "Freigeben" sichtbar, aber Einplanen separat unter Calendar/Posts
   - Anna will "publish & schedule" in einem Modal
   - Empfehlung: Neben "Freigeben"-Button ein Dropdown "Freigeben & Einplanen für Mittwoch"

---

## Persona 3: Robert — Reviewer (QA/Compliance)

**Goal:** "Ich bin Robert, QA/Zukunftsbund. Ich will Pipeline-Health überwachen, Cost tracken, Compliance verifizieren, neue Embedding-Modelle canary-deployen."

### Journey-Tabelle

| Schritt | Was sieht Robert | Was tut er | Friction (Severity) |
|---------|---|---|---|
| 1. Login → Admin? | Layout.jsx Zeile 54–56 zeigt "Admin" section mit nur 1 Item: `/admin/models/backtest` (AdminModels) | Robert klickt "Modelle" | 🟡 **Admin-Tab versteckt unten** — sollte oben sein oder separater Bereich |
| 2. Daily Cost-Check | Robert navigiert zu `/settings/analytics` → LLMAnalytics.jsx Zeile 83–200+ zeigt TrendsCacheTab | Sieht Cost-Trend LineChart (30 Tage), HBar für "Top Killers" Modelle, Heatmap (7×24 hour grid) (Zeile 122–130) | 🔵 Recharts-Visualisierung professionell |
| 3. Cache-Hit-Rate Trend | LLMAnalytics.jsx Zeile 154–184 zeigt Cache-Hit-Rate als Prozentsatz | Robert sieht avg_7d und Alert wenn <30% (Zeile 177–183) — kann CSV herunterladen (Zeile 161) | 🔵 Alert-System ok |
| 4. Throttle-Events suchen | LLMAnalytics.jsx hat `getRunawayDetection()` (Zeile 16) — wird in Heatmap visualisiert aber Code nicht vollständig sichtbar | Robert sieht Top Killers + Heatmap, aber unklar wie er "Throttle-Events filtern" soll | 🟡 **Runaway-Detection-UI unvollständig im Code** — kann nicht sehen wie Robert Alerts acknowlegt |
| 5. Brand-Voice Drift Review | Sidebar → Brand Voice → "Review-Queue" (Layout.jsx Zeile 47) = `/brand-voice/review-queue` (ReviewQueue.jsx — nicht gelesen) | Robert navigiert dort | 🔵 Pfad vorhanden |
| 6. Compliance: llm_call_logs Audit | Robert braucht Audit-Trail für DSGVO — muss in DB oder Admin-Panel nachschauen | Keine sichtbare UI für "Logs ansehen" in gelesenen Komponenten | 🔴 **Keine Audit-Trail-UI** — Robert kann nicht self-serve nachschauen ob API-Keys in Logs sind, muss SSH |
| 7. RtbF-Delete initiieren | Robert will einen Tenant löschen (Recht auf Vergessen) — Settings zeigt `/settings/data-deletion` (DataDeletion.jsx — nicht gelesen) | Klickt → hoffentlich gibt es ein "Delete Tenant Data" Modal | 🟡 **DataDeletion.jsx nicht gelesen** — kann nicht verifizieren ob UI sicher enough ist (z.B. Confirmation oder nur 1 Click?) |
| 8. Embedding-Modell Canary | Robert will neues Embedding-Modell für 10% der Tenants deployen | Keine UI in AdminModels.jsx für Canary-Deployment sichtbar (Zeile 15 App.jsx: nur `/admin/models/backtest`) | 🔴 **Kein Modell-Management-UI für neue Model Rollout** — Robert muss Code ändern oder SSH |
| 9. Monitoring: Alert-Dashboard | Robert braucht täglich neue Alerts (RuntimeError, High-Cost, Cache-Down) | LLMAnalytics.jsx hat Alert-System (Zeile 177: cacheAlert), aber zentrales Anomaly-Dashboard nicht lesbar | 🟡 **Anomaly-Detection-UI unvollständig** — getLLMAnalyticsAnomaly() importiert aber nicht genutzt im Code-Ausschnitt |

### Top-3 Pain-Points für Robert

1. **🔴 Keine Audit-Trail-UI für DSGVO-Compliance**
   - Robert kann nicht selbst nachschauen ob Tenant-Daten korrekt gelöscht wurden oder Logs sauber sind
   - Empfehlung: Neuer `/admin/audit-logs` mit Filter (Tenant, Date-Range, Action, Status) + CSV-Export

2. **🔴 Kein Model-Management für Canary-Rollout**
   - AdminModels.jsx beschreibt nur "Backtest", nicht "Deploy neues Modell zu X% der Tenants"
   - Empfehlung: `/admin/models` mit Tabelle: Modell, % Deployment, Health, Rollback-Button

3. **🟡 Runaway-Detection + Throttle-Events Heatmap zu granular, nicht actionable**
   - Heatmap zeigt 7×24 Grid (168 Zellen), aber unklar: Ist Rot = stoppen? = monitoren?
   - Empfehlung: Heatmap mit Klick → "Top Queries in Stunde XY" + "Automatic Throttle Applied?"

---

## Cross-Persona Findings

### 🔴 Critical Blockers (Severity 🔴)

1. **Fehlende Breadcrumb-Navigation überall**
   - Nach mehreren Klicks: Woher bin ich gekommen? Wo bin ich jetzt?
   - Files: Layout.jsx (keine Breadcrumb), App.jsx (Routing ok aber keine Breadcrumb-Komponente)
   - Empfehlung: `<Breadcrumb path={location.pathname} />` in Main-Content

2. **Fehlende Audit-Trail-UI**
   - Robert kann nicht DSGVO-Compliance verifizieren self-serve
   - Empfehlung: `/admin/audit-logs` mit Full-Text-Search, CSV-Export

3. **Kein Model-Rollout-UI**
   - Robert kann kein neues Embedding-Modell deployen ohne SSH
   - Empfehlung: `/admin/models` mit Canary%-Slider + Rollback

### 🟡 Major Frictions (Severity 🟡)

1. **Zu viele Sidebar-Items (18 gesamt) — Cognitive Overload**
   - Layout.jsx Zeile 29–56: 12 Main + 5 BrandVoice + 1 Admin
   - Empfehlung: Collapsible Groups, oder "Context-Sensitive Nav" (Daily Driver nur `/ideas`, `/posts`, `/calendar`)

2. **Loading-States sind nur Text, nicht animiert**
   - Ideas.jsx Zeile 42: "Lade Fragen..." ohne Spinner
   - WizardPage.jsx: Synthesis nach Phase 4 gibt keine Rückmeldung
   - Empfehlung: `<Loader2 className="animate-spin w-4 h-4" />` + "KI arbeitet..." Text

3. **Post-Freigeben + Einplanen sind 2 Klicks statt 1**
   - Anna muss zu `/calendar` oder einen zusätzlichen Dialog öffnen
   - Empfehlung: Modal nach "Freigeben"-Click: "Jetzt einplanen?" mit Date/Time-Picker

4. **Wizard Phase 3 mit 9 Fragen zu lang**
   - WizardPage.jsx Zeile 85–138: 9 offene Fragen ohne Abkürzung
   - Session-Abbruch-Risiko
   - Empfehlung: Max 5 pro Phase, "Skip optional question" für Demographics

5. **Keine Step-by-Step Roadmap nach Brand-Voice Wizard**
   - Eric weiß nach Finalisierung nicht was nächstes ist
   - Empfehlung: Modal mit "Nächste 3 Schritte: [1] Quellen [2] Ideen [3] Post" + inline-Links

6. **Fehlende Quick-Generate auf Dashboard**
   - Anna muss zu `/ideas` um manuelle Idee zu erstellen
   - Empfehlung: Dashboard-Card "Neue Idee erstellen" + inline-Textfeld

### 🔵 Polish Issues (Severity 🔵)

1. **Sidebar-Items-Reihenfolge nicht priorisiert**
   - Core User Journey sollte Top 3 Items sein: Dashboard, Ideen, Posts
   - Jetzt: In Reihenfolge aber nicht grouped
   - Empfehlung: Gruppe "Arbeitsablauf" (Ideen, Posts, Calendar) vs "Konfiguration" (Brand Voice, Einstellungen)

2. **Mobile-Responsiveness der Setup-Checkliste**
   - Dashboard.jsx Zeile 766: 4-Spalten-Grid könnte zu klein sein auf Mobile
   - Empfehlung: 1–2 Spalten auf Mobile, Accordion-Modus

---

## Top-10 UX-Schmerzen sortiert nach Severity

| # | Schmerz | Severity | Betroffene | File:Line | Fix-Aufwand |
|---|---------|----------|-----------|-----------|------------|
| 1 | Keine Audit-Trail-UI für DSGVO | 🔴 | Robert | (nicht vorhanden) | Hoch |
| 2 | Kein Model-Rollout-UI (Canary) | 🔴 | Robert | AdminModels.jsx | Hoch |
| 3 | Fehlende Breadcrumb-Navigation | 🔴 | Alle | Layout.jsx | Mittel |
| 4 | 18 Sidebar-Items — Cognitive Overload | 🟡 | Anna, Eric | Layout.jsx:29–56 | Mittel |
| 5 | Loading-States nur Text, nicht animiert | 🟡 | Alle | Ideas.jsx:42, WizardPage.jsx | Niedrig |
| 6 | Post-Freigeben + Einplanen = 2 Klicks | 🟡 | Anna | Posts.jsx, Calendar.jsx | Niedrig |
| 7 | Wizard Phase 3 zu lang (9 Fragen) | 🟡 | Eric | WizardPage.jsx:85–138 | Mittel |
| 8 | Keine Roadmap nach Wizard-Ende | 🟡 | Eric | WizardPage.jsx:13 | Niedrig |
| 9 | Keine Quick-Generate auf Dashboard | 🟡 | Anna | Dashboard.jsx | Niedrig |
| 10 | Runaway-Detection Heatmap zu granular | 🟡 | Robert | LLMAnalytics.jsx:122–130 | Mittel |

---

## Empfehlungen nächste Schritte (Priorisiert)

### P0 (Sprint 3B)
- [ ] Breadcrumb-Navigation implementieren (Layout.jsx)
- [ ] Loading-States mit Spinner-Icons (Ideas.jsx, WizardPage.jsx)
- [ ] Quick-Generate-Card auf Dashboard

### P1 (Sprint 3C)
- [ ] Sidebar-Navigation reorganisieren (groups collapsible)
- [ ] Post-Freigeben + Einplanen in 1-Modal
- [ ] Wizard Phase 3: Fragen reduzieren auf Max 5

### P2 (Sprint 4)
- [ ] Audit-Trail-UI (/admin/audit-logs)
- [ ] Model-Rollout-Management (/admin/models)
- [ ] Brand-Voice Wizard: "Nächste Schritte"-Modal

---

## Messbarkeitsmetriken (für A/B-Tests später)

- **Time-to-First-Post**: Wie lang vom Login bis Post veröffentlicht (Target: <15 min für Daily Driver)
- **Wizard-Completion-Rate**: % von Usern die Brand-Voice Wizard finished (Target: >85%)
- **Admin-Efficiency**: Zeit von Robert bis Audit-Log angesehen (Target: <2 min)
- **Sidebar-Click-Depth**: Durchschnittliche Clicks bis zu Core-Action (Target: <2 Clicks)

---

**Audit erstellt:** 2026-05-04 | Code-Basis: frontend/src (App.jsx, Layout.jsx, Dashboard.jsx, WizardPage.jsx, BrandVoice.jsx, Posts.jsx, Ideas.jsx, LLMAnalytics.jsx)
