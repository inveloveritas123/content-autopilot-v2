# GitHub Setup Audit — content-autopilot-v2

**Datum:** 2026-06-12
**Repo:** inveloveritas123/content-autopilot-v2
**Auditor:** Claude Code (automatisiert, read-only)

---

## 1. Branches

### 1a. Nicht-Dependabot-Branches

| Branch | Letzter Commit | Prefix | Ahead/Behind main | Inhalt vs. main | Status |
|--------|----------------|--------|-------------------|-----------------|--------|
| `main` | 2026-06-12T14:22Z | `[arch]` | — | Basis | Aktiv |
| `arch/weekloop` | 2026-06-12T13:40Z | `[arch]` | +1 / -1 | 1 Commit: `[arch] feat(p08): #15 — p08 auf LLM-Seam (Requesty S6)` | Aktiv, PR fehlt |
| `knecht/rewire-green` | 2026-06-12T14:22Z | `[knecht]` | +5 / -1 | 5 Commits: gitleaks-Allowlist (2x), package-lock.json sync, Prettier/ESLint-Fix, CI Hygiene-Job Fix | Aktiv, PR #31 offen (→ feat/files-as-source-of-truth) |
| `feat/files-as-source-of-truth` | 2026-06-12T09:53Z | kein Prefix | 0 / -5 | 0 eigene Commits mehr, vollständig hinter main | Stale — PR #28 gemergt, Branch wäre löschbar |
| `feat/issue-148-phase8` | 2026-05-04T23:00Z | kein Prefix | 0 / -45 | 0 eigene Commits mehr, 45 Commits hinter main | Stale — Closes #148 (Phase 8), sehr alt, löschbar |

### 1b. Dependabot-Branches

**11 Dependabot-Branches** (alle auf `main` gerichtet, alle offen als PRs #1–#13):
- 3x GitHub Actions: `actions/setup-python-6`, `gitleaks-action-3`, `upload-artifact-7`
- 5x npm (frontend): `build-tooling`, `linting`, `lucide-react-1.17.0`, `react-stack`, `recharts-3.8.1`
- 5x pip (backend): `celery-5.6`, `fastapi-stack`, `llm-providers` (anthropic 0.49→0.107!), `openpyxl`, `sqlalchemy-stack`

**Keiner dieser PRs ist gemergt.** Der anthropic-Bump (0.49→0.107) ist besonders relevant.

---

## 2. Pull Requests

### Alle PRs (offen + gemergt, letzte 20)

| # | Titel | State | Head → Base | Erstellt | Gemergt/Geschlossen | Blockiert? |
|---|-------|-------|------------|----------|---------------------|-----------|
| 31 | [knecht] PR#28 grün: Gitea raus, Tests grün, 2 Bugfixes, ruff-Baseline + Container-Deploy | OPEN | knecht/rewire-green → feat/files-as-source-of-truth | 2026-06-12 | — | Ja: Base-Branch feat/files-as-source-of-truth ist gemergt → PR hängt |
| 28 | Louis als Source of Truth: content-truth + Prompt-Studio + LLM-Seam (P1–P5) | MERGED | feat/files-as-source-of-truth → main | 2026-06-12 | 2026-06-12T13:54Z | — |
| 13 | chore(deps): bump recharts 2.15.4→3.8.1 | OPEN | dependabot/recharts → main | 2026-06-02 | — | — |
| 12 | chore(deps): bump lucide-react 0.460→1.17.0 | OPEN | dependabot/lucide-react → main | 2026-06-02 | — | — |
| 11 | chore(deps-dev): bump linting group (6 updates) | OPEN | dependabot/linting → main | 2026-06-02 | — | — |
| 10 | chore(deps-dev): bump build-tooling group (6 updates) | OPEN | dependabot/build-tooling → main | 2026-06-02 | — | — |
| 9 | chore(deps): update openpyxl >=3.1.0→>=3.1.5 | OPEN | dependabot/openpyxl → main | 2026-06-02 | — | — |
| 8 | chore(deps): update celery ==5.4.*→==5.6.* | OPEN | dependabot/celery → main | 2026-06-02 | — | — |
| 7 | chore(deps): update anthropic ==0.49.*→==0.107.* | OPEN | dependabot/llm-providers → main | 2026-06-02 | — | — |
| 6 | chore(deps): bump react-stack group (5 updates) | OPEN | dependabot/react-stack → main | 2026-06-02 | — | — |
| 5 | chore(deps): bump sqlalchemy-stack group (2 updates) | OPEN | dependabot/sqlalchemy-stack → main | 2026-06-02 | — | — |
| 4 | chore(deps): bump fastapi-stack group (4 updates) | OPEN | dependabot/fastapi-stack → main | 2026-06-02 | — | — |
| 3 | chore(ci): bump actions/setup-python 5→6 | OPEN | dependabot/setup-python → main | 2026-06-02 | — | — |
| 2 | chore(ci): bump gitleaks/gitleaks-action 2→3 | OPEN | dependabot/gitleaks-action → main | 2026-06-02 | — | — |
| 1 | chore(ci): bump actions/upload-artifact 4→7 | OPEN | dependabot/upload-artifact → main | 2026-06-02 | — | — |

**Problem:** PR #31 richtet sich gegen `feat/files-as-source-of-truth` (bereits gemergt nach main). Knechts 5 Commits müssen in einen neuen PR gegen `main` umgeleitet werden.

---

## 3. Issues (Offene Issues — vollständige Tabelle)

| # | Titel | Labels | Zuordnung | Board-Bahn | Status-Einschätzung |
|---|-------|--------|-----------|------------|---------------------|
| 42 | [Modelle] Entscheid Opus vs. Sonnet-EU + Gemini-Remap revidieren (Robert) | architekt | Architekt | — / Mensch-Input nötig | Offen, Entscheidung durch Robert |
| 41 | [P17] Board-Ausrichtung (je-Transkript-Beobachter) + voice_drift auf LLM-Seam | architekt | Architekt | 2 / technisch | Offen |
| 40 | [Setup] Voice-Fallback wenn keine Voice-Quelle (Bahn 2) | architekt | Architekt | 2 | Offen |
| 39 | [Setup] P02 Website-Analyse implementieren (Bahn 2) | architekt | Architekt | 2 | Offen |
| 38 | [Qualität] Quality-Gate vom Stub zum echten Scorer (Final-Gate, Bahn 5) | architekt | Architekt | 5 | Offen |
| 37 | [Telegram] P16-Feedback-Loop 'nochmal anders' (Bahn 5) | architekt | Architekt | 5 | Offen |
| 36 | [Telegram] Intent-Routing freier Chat-Modus (P09 on-demand + P13 eigene Idee) | architekt | Architekt | 4/5 | Offen |
| 35 | [Telegram] P07-Research-Findings als Chat-Push (Bahn 4 / Pfad A) | architekt | Architekt | 4 | Offen |
| 34 | [Infra] Test-/CI-Umgebung: Python-Version + fehlende Test-Deps angleichen | knecht | Knecht | technisch | Offen — teilweise durch .python-version=3.12 in knecht/rewire-green adressiert, aber nicht gemergt |
| 33 | P03/P01: Prompt liefert Markdown statt kanonischem JSON → Setup-Pipeline-E2E bricht | architekt | Architekt | technisch | Offen — aktives Problem |
| 32 | [knecht] Server-E2E: Setup-Pipeline mit Eric-Transkript → kanonische Validierung | knecht | Knecht | technisch | Offen |
| 30 | [Gates] F1: 29 ungepinnte '-latest'-Modelle → pinnen oder Policy-Ausnahme | architekt | Architekt | technisch | Offen |
| 29 | [Schema] Konsumenten auf kanonisches Louis-Schema umstellen (gradual rewire nach P0x-Write-Path) | architekt | Architekt | technisch | Offen |
| 27 | [Frontend] Prompt-Studio: 422-Schema-Fehler zeigt [object Object] + Build/visuelle Prüfung | KEIN LABEL | unklar | technisch | **Hygiene: kein Label** — wahrscheinlich durch PR #28 (P1-P5-Overlay + Validierung) zumindest teilweise erledigt — prüfen |
| 26 | [Schema] _meta-Rehydration: agentur_id hardcoded + leere prompt_version-Hash-Tabelle | architekt | Architekt | technisch | Offen |
| 25 | [Schema] v2-Prompts extrahieren viele Louis-Pflichtfelder nicht → Validierung scheitert | architekt | Architekt | technisch | Offen — vermutlich mit #29 verwandt |
| 24 | [Deploy] SSH-Erreichbarkeit Port 10022 für GitHub-Runner unverifiziert | knecht | Knecht | technisch | Offen |
| 23 | [Architektur] content-truth :ro-Mount blockiert Prompt-Studio-Schreibzugriff (P3) | KEIN LABEL | unklar | technisch | **Wahrscheinlich erledigt** — PR #28 hat content-truth-Mounts + Overlay implementiert (Commit 35c59c3) |
| 22 | [Prompt] P17 lädt mit leerem System-Prompt (kein ## System-Prompt-Heading) | KEIN LABEL | unklar | technisch | **Prüfung:** P17-Datei hat `## Block 1: PROMPT_ROLLE (System-Prompt — ready to paste)` aber KEIN `## System`-Heading der App-Parser erwartet — Issue vermutlich noch offen |
| 20 | [Seam2 6/6] E2E-Durchlauf + Tenant-Opt-in + Tests | architekt, enhancement, backend, test | Architekt | 2 | Offen — letzte Seam2-Stufe |
| 19 | [Seam2 5/6] [BLOCKER] Content-Generierung an Session-Abschluss (Variante B) | architekt, enhancement, backend, **blocker** | Architekt | 2 | BLOCKER |
| 18 | [Seam2 4/6] Idempotenz gegen Doppel-Verarbeitung | architekt, enhancement, backend | Architekt | 2 | Offen |
| 17 | [Seam2 3/6] Folgefrage / Abschluss per Telegram zurücksenden | architekt, enhancement, backend | Architekt | 2 | Offen |
| 16 | [Seam2 2/6] Inbound-Routing in telegram_task verdrahten | architekt, enhancement, backend | Architekt | 2 | Offen |
| 15 | [Seam2 1/6] [BLOCKER] LLM-Pfad: p08 + layer1 auf llm_service umstellen | architekt, enhancement, backend, **blocker** | Architekt | 2 | **Teilweise erledigt** — p08 durch arch/weekloop, aber layer1 laut Commit-Message noch offen; kein PR gemergt |

**Gesamt offene Issues:** 25

### 3a. Issues OHNE architekt/knecht-Label

| # | Titel | Problem |
|---|-------|---------|
| 27 | [Frontend] Prompt-Studio 422-Fehler | Label fehlt komplett |
| 23 | [Architektur] content-truth :ro-Mount | Label fehlt komplett |
| 22 | [Prompt] P17 leerem System-Prompt | Label fehlt komplett |

### 3b. Wahrscheinliche Duplikate / Verwandte Issues

| Gruppe | Issues | Begründung |
|--------|--------|------------|
| Schema-Konsumenten | #25, #26, #29 | Alle betreffen kanonisches Louis-Schema, Pflichtfelder-Extraktion und Migration — könnten zu einem Epic konsolidiert werden |
| Secret-Scrub (historisch) | Nicht mehr offen — kein aktuelles Duplikat gefunden | — |

**Hinweis:** #14 und #21 wurden im Auftrag als mögliche Duplikate genannt, sind aber nicht unter den aktuell offenen Issues — beide scheinen bereits geschlossen.

### 3c. Issues die durch gemergte Arbeit erledigt sein müssten

| # | Titel | Begründung Erledigung |
|---|-------|----------------------|
| 23 | content-truth :ro-Mount blockiert Prompt-Studio | PR #28 (Commit 8668784) implementiert explizit "content-truth-Mounts + Auto-Deploy-Workflow + setup-Preflight" und Commit 35c59c3 "Prompt-Studio API + UI zum Bearbeiten/Validieren/Speichern der content-truth (Overlay)" — :ro-Mount-Problem gelöst |
| 27 | 422-Schema-Fehler (Prompt-Studio) | PR #28 bringt P1-P5 + Validierung; teilweise erledigt — Restrisiko: Build/visuelle Prüfung auf Server B noch ausstehend laut Issue |

**Issue #22 (P17 leerer System-Prompt):** Audit der Datei zeigt `## Block 1: PROMPT_ROLLE (System-Prompt — ready to paste)` ist vorhanden, aber kein exaktes `## System Prompt`-Heading-Pattern. Ob die App dieses Heading korrekt parst, hängt vom Parser ab — Issue ist vermutlich NOCH OFFEN. Nicht schließen ohne Server-E2E-Verifikation.

### 3d. Blocker-Label-Korrektheit

| # | Blocker-Label | Bewertung |
|---|---------------|-----------|
| 19 | Ja | Korrekt — Content-Generierung an Session-Abschluss ist echter Blocker für Bahn 2 |
| 15 | Ja | Teilweise korrekt — p08 erledigt, aber layer1 fehlt noch → Blocker reduziert sich auf layer1 |

---

## 4. CI-Workflows

### Vorhandene Workflows

`.github/workflows/` enthält 11 Dateien:
`container-scan.yml`, `deploy.yml`, `e2e-explore.yml`, `e2e-smoke.yml`, `eval-quality-gate.yml`, `eval.yml`, `frontend-tests.yml`, `lint.yml`, `secret-scan.yml`, `security-tests.yml`, `tests.yml`

### Letzter Stand auf `main` (2026-06-12T14:22Z)

| Workflow | Status | Ergebnis |
|----------|--------|----------|
| Deploy (Server B) | completed | **SUCCESS** |
| Tests (pytest) | completed | **SUCCESS** |
| Secret Scan (gitleaks) | completed | **SUCCESS** |
| E2E Smoke (Playwright) | completed | **FAILURE** |
| Lint (ruff + eslint + prettier) | completed | **FAILURE** |

**main ist NICHT grün — 2 von 5 Workflows rot.**

### CI-Fehler-Details

**E2E Smoke (Playwright) — FAILURE:**
`docker compose` bricht beim Start ab weil die Secret-Variable `NEXTCLOUD_PASSWORD` in `.env` nicht gesetzt ist. Fehlermeldung: `required variable NEXTCLOUD_PASSWORD is missing a value: set NEXTCLOUD_PASSWORD in .env`. Der gesamte Container-Stack startet nicht → Playwright-Tests laufen nie.

**Lint (ruff + eslint + prettier) — FAILURE:**
`npm ci` schlägt fehl weil `package-lock.json` nicht in Sync mit `package.json` ist. Fehlende Einträge: `@eslint/js@9.39.4`, `eslint@9.39.4`, `prettier@3.8.4`, `@playwright/test@1.60.0` und ~30 weitere transitive Deps. **Hinweis:** `knecht/rewire-green` (PR #31) enthält genau diesen Fix — aber PR ist gegen den falschen Base-Branch gerichtet und noch nicht gemergt.

### Letzter Stand auf `knecht/rewire-green` (2026-06-12T14:23Z)

| Workflow | Status | Ergebnis |
|----------|--------|----------|
| Tests (pytest) | completed | **SUCCESS** |
| Secret Scan (gitleaks) | completed | **SUCCESS** |
| Lint (ruff + eslint + prettier) | completed | **FAILURE** (gleicher npm ci Fehler — Fix im Branch selbst noch nicht wirksam?) |

---

## 5. Koordinations-Konvention

### Commit-Präfix-Disziplin (letzte 15 Commits auf main)

```
e4ce007 [arch] docs: Vision & Projektplan + Figma-SOLL-IST-Abgleich (2026-06-12)
477e484 [knecht] fix(test): Tier-Assertions an EU-Modell-IDs angepasst
60a55bc [knecht] fix(llm): EU-souveräne Modell-IDs hinterlegt
096391e [knecht] fix+test+style: PR#28 grün — Pollution-Fix, 2 Bugfixes, ruff-Baseline
781a5d1 [knecht] chore(gitea): Gitea vollständig entfernt, CLAUDE.md dekodiert
1f535db docs: Server-E2E Bootstrap-Prompt          ← KEIN PRÄFIX
dd48ae7 feat(safety): Profil-Feld-Editor read-only ← KEIN PRÄFIX
43e419a refactor(voice_drift): ...                 ← KEIN PRÄFIX
7199c9c chore(werkbank): D3-Secret-Scan Allowlist  ← KEIN PRÄFIX
2001434 fix(p12)+feat(facade): ...                 ← KEIN PRÄFIX
2151e63 feat(settings): Modell-Hoheit pro Phase    ← KEIN PRÄFIX
0830848 feat(pipeline): P01/P03/P04 schreiben nativ Louis-kanonisch ← KEIN PRÄFIX
dddf8f3 docs: Plaene, Louis-ADRs, DEPLOY, ...      ← KEIN PRÄFIX
8668784 chore(deploy): content-truth-Mounts + Auto-Deploy ← KEIN PRÄFIX
35c59c3 feat(prompt-studio): API + UI zum Bearbeiten ← KEIN PRÄFIX
```

**Befund:** Von 15 Commits tragen nur 5 einen `[arch]`/`[knecht]`-Präfix. 10 Commits — der gesamte feat/files-as-source-of-truth-Merge-Strom — haben keinen Agenten-Präfix. Dies ist der Zeitraum vor Einführung der Konvention (PR #28 war der Übergang). Ab Commit e4ce007 wird die Konvention eingehalten.

**arch/weekloop:** 1 Commit, korrekt `[arch]`-gepräfixt, mit Co-Author-Tag.

**knecht/rewire-green:** 5 Commits, alle korrekt `[knecht]`-gepräfixt, alle mit Co-Author-Tag (`Claude Opus 4.8 (Knecht)`).

### Co-Author-Konvention

Beide aktiven Agents (arch + knecht) fügen korrekt Co-Author-Tags ein. Konvention wird seit PR #28 eingehalten.

### COORDINATION.md — Veraltungsgrad

COORDINATION.md ist **stark veraltet**:

1. **Gitea-Referenzen (3x):** Kommunikationskanal, QA-Monitor und Rollen-Abschnitt verweisen alle auf Gitea. Gitea wurde in Commit `781a5d1` vollständig entfernt.
2. **Stand-Datum:** `2026-04-12, 14:30` — 2 Monate alt, Feature-Tabelle beschreibt einen vollständig anderen Systemzustand (keine Louis-Pipeline, keine content-truth, keine Seam2).
3. **Rollen-Beschreibung:** "Cowork (Windows)" und "QA-Monitor alle 5min" existieren nicht mehr in dieser Form.
4. **Issue-Liste:** Zeigt Issues #1–#9 aus dem Gitea-Zeitraum — vollständig irrelevant für GitHub-Issues.

COORDINATION.md muss vollständig neu geschrieben werden.

---

## 6. Empfohlene Hygiene-Aktionen

### Priorität 1 (sofort — blockiert CI/Merge-Pfad)

**A. PR #31 auf `main` umlenken (oder neu erstellen)**
PR #31 (`knecht/rewire-green` → `feat/files-as-source-of-truth`) ist hängend, weil der Base-Branch gemergt ist. Aktion: Base-Branch auf `main` ändern (via GitHub UI: "Edit" im PR) oder PR schließen + neuen PR `knecht/rewire-green → main` erstellen. Die 5 Commits (npm-Lock-Fix, gitleaks-Allowlist, Lint-Fix, CI-Hygiene) lösen direkt den Lint-Fehler auf main.

**B. CI-Secret `NEXTCLOUD_PASSWORD` für E2E-Smoke bereitstellen**
`e2e-smoke.yml` lädt `docker-compose.v2.yml` welches `NEXTCLOUD_PASSWORD` als required Variable hat. Entweder: (1) Secret in GitHub-Repository-Secrets hinterlegen, oder (2) `e2e-smoke.yml` so anpassen, dass eine Dummy-Variable mit Default gesetzt wird, wenn die Variable für CI nicht notwendig ist. Bis dahin ist E2E auf main permanent rot.

### Priorität 2 (diese Woche — Backlog-Hygiene)

**C. Issue #23 schließen**
`content-truth :ro-Mount blockiert Prompt-Studio` — durch PR #28 (Commits 8668784 + 35c59c3) implementiert. Issue mit Referenz auf den Merge-Commit schließen.

**D. Issues #22, #23, #27 labeln**
Alle drei haben kein `architekt`/`knecht`-Label. Zuweisung:
- #27 (422-Fehler im Frontend) → `knecht` + `frontend`
- #23 (erledigt) → schließen (s.o.)
- #22 (P17 Heading) → `architekt` (Prompt-Parser-Frage, gehört zur Wiring-Architektur)

**E. Issue #15 Blocker-Scope korrigieren**
`[Seam2 1/6] [BLOCKER]` ist nur noch halb-blockiert: p08 ist durch `arch/weekloop` erledigt, layer1 fehlt. Entweder: Commit-Link in Issue hinzufügen + Titel auf `[Seam2 1/6] [BLOCKER] layer1 auf llm_service umstellen` kürzen, oder Issue für p08 schließen und neues Issue für layer1 erstellen.

### Priorität 3 (nächster Wochenloop — Aufräumen)

**F. Stale Branches löschen**
- `feat/files-as-source-of-truth`: PR #28 gemergt, Branch 0 Commits ahead — löschen.
- `feat/issue-148-phase8`: 45 Commits behind, letzter Commit 2026-05-04 — löschen.

**G. COORDINATION.md vollständig neu schreiben**
Inhalt ist für Gitea-Ära geschrieben. Neuer Inhalt muss abdecken:
- Kommunikationskanal: GitHub Issues (nicht Gitea)
- Rollen: `[arch]` (Opus, Mac, lokal) vs. `[knecht]` (Server B, Claude Code)
- Commit-Konvention: `[arch]/[knecht]`-Präfix + Co-Author-Tag
- Branch-Strategie: `arch/*` und `knecht/*` → PR gegen `main` (nicht gegen Feature-Branches)
- Issue-Labels: `architekt`, `knecht`, Board-Bahnen 1–5
- Aktuelle Issue-Tracker-Übersicht (Link zu GitHub Projects falls vorhanden)

**H. Dependabot-PR #7 priorisieren**
`anthropic ==0.49.*→==0.107.*` ist ein Major-Gap von 58 Minor-Versionen. Die anderen Dependabot-PRs (CI-Actions, eslint, recharts) können gebatch werden — #7 sollte einzeln reviewt und gemergt werden, sobald der Lint-Fix (Priorität 1A) durch ist.

**I. Schema-Issues #25/#26/#29 zu Epic konsolidieren**
Alle drei beschreiben dasselbe Problem aus verschiedenen Winkeln: Louis-Schema-Migration. Empfehlung: ein Tracking-Issue als Epic anlegen, die drei als Sub-Issues referenzieren, um Backlog-Rauschen zu reduzieren.

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Nicht-Dependabot-Branches (remote) | 5 (main + arch/weekloop + knecht/rewire-green + feat/files-as-source-of-truth + feat/issue-148-phase8) |
| Dependabot-Branches | 11 |
| PRs gesamt (alle States) | 15 |
| PRs offen (human) | 1 (PR #31, hängt) |
| PRs offen (Dependabot) | 13 |
| PRs gemergt | 1 (PR #28) |
| Offene Issues | 25 |
| CI auf main | Deploy OK, Tests OK, Secrets OK — **Lint ROT, E2E Smoke ROT** |
