# Contributing — Content Autopilot v2

Dieses Dokument beschreibt den Pflicht-Workflow fuer alle Beitraege (Knecht-Agents + menschliche Entwickler). Verstaesse gegen diese Regeln sind BLOCKING im Cowork-Review.

---

## Setup (einmalig nach Clone)

```bash
# 1. Pre-Commit installieren (Quality-Gates lokal vor jedem Commit)
pip install pre-commit
pre-commit install

# 2. Backend-Tooling
cd backend
pip install -r requirements.txt
pip install ruff==0.7.4 pytest pytest-asyncio  # Dev-Tools

# 3. Frontend-Tooling
cd ../frontend
npm ci
```

**Pre-Commit-Hooks** (laufen automatisch bei `git commit`):

- `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`, `check-merge-conflict`, `detect-private-key`, `check-added-large-files` (max 2 MB)
- `ruff` (Python lint) + `ruff-format` (Python format) auf `backend/`
- `prettier` auf `frontend/src/`
- `eslint` auf `frontend/src/`
- `gitleaks` (Secret-Scan, lokales Pendant zum CI-Workflow)

Manuell ueber alles laufen lassen: `pre-commit run --all-files`.

**Wer Pre-Commit umgehen will**, muss `git commit --no-verify` schreiben und im PR-Body begruenden. Die CI-Workflows fangen dieselben Probleme aber nochmal — Umgehen wird also nur dann durchgehen, wenn der Commit auch wirklich sauber ist.

---

## Branch-Strategie

- `main` ist der stabile Branch. **Kein direkter Push auf main.**
- Feature-Branches: `feat/issue-NNN-kurz` (Beispiel: `feat/issue-149-deletion-fk`)
- Bugfix-Branches: `fix/issue-NNN-kurz`
- Doku-Branches: `docs/issue-NNN-kurz`
- Hotfixes: `hotfix/NNN-kurz` — gehen direkt gegen main, brauchen aber manuellen Review

```bash
git checkout -b feat/issue-154-doku-foundation
# ... aendern ...
git push -u origin feat/issue-154-doku-foundation
```

---

## Commit-Messages (Conventional Commits)

Format: `<typ>(<scope>): <kurze Beschreibung> (#NNN)`

Typen:
- `feat` — neue Funktion
- `fix` — Bugfix
- `docs` — nur Dokumentation
- `chore` — Build, Abhaengigkeiten, Konfiguration
- `refactor` — Umstrukturierung ohne Verhalten-Aenderung
- `test` — Tests hinzufuegen oder korrigieren
- `perf` — Performance-Verbesserung

Beispiele:
```
feat(throttle): Throttle-Layer pro Tenant + Global advisory-lock gehaertet (#156)
fix(dsgvo): deletion_request_id FK Backfill in Migration 047 (#149)
docs(adr): ADR-0001 bis ADR-0005 Doku-Foundation (#154)
```

Issue-Referenz am Ende ist Pflicht. Ohne Issue-Nummer: nur bei Trivial-Fixes (typo, fehlendes Komma).

---

## Soll-Ist-Pflicht vor jeder Aenderung (Constraint #14)

Bevor Code geaendert wird:

1. Aktuellen Repo-Stand der betroffenen Datei lesen: `git log --oneline -5 <datei>`
2. NICHT blind der Issue-Beschreibung vertrauen (Issues koennen stale sein)
3. SOLL (Issue) vs. IST (Repo) als Comment im Issue dokumentieren: "SOLL: X. IST: Y. Differenz: Z."
4. Bei Mismatch: **STOP** und im Issue nachfragen, nicht drueberbuegeln

---

## Migration-Workflow (Constraint #10/#11)

Bei **jeder** DB-Aenderung:

1. **Backup zuerst** — `scripts/safe_alembic.sh` macht das automatisch
2. **Ausfuehren auf Host** — `scripts/safe_alembic.sh "upgrade head"` (NICHT im Container)
3. **Verify** — `alembic current` muss `head` zeigen
4. **Container-Restart** wenn Schema-Aenderung: `docker compose restart backend-v2`

```bash
# Pflicht-Reihenfolge
scripts/safe_alembic.sh "upgrade head"
docker compose exec backend-v2 alembic current
docker compose restart backend-v2
```

**Nie direkt `alembic upgrade head` im Container.** Das Backup-Script laueft nicht unter Container-Rechten.

---

## Review-Loop

Jeder PR durchlaeuft:

1. Knecht implementiert + pushed
2. Knecht kommentiert im Issue: `Fix gepusht in <commit>. Bitte testen. Tests: [...]`
3. Cowork Auto-Review: Verdict APPROVE / CHANGES REQUESTED / DISCUSSION
4. Bei APPROVE: Label `awaiting-robert-verify` gesetzt, Issue bleibt **offen**
5. Robert prueft und schliesst

**Max. 2 Iterationen** (Implementer → Reviewer → Implementier-Korrektur → Reviewer) bevor architect eskaliert wird.

---

## Issue-Schliessen — Robert ist Gate (Constraint #12)

Knecht schliesst Issues **nie selbst**, ausser:
- Reine Doku-Issues ohne Code-Impact
- Pure Refactor-Issues ohne User-sichtbare Aenderung mit gruenen Tests UND Cowork-Approve
- Trivial-Bugs (typo, fehlendes Import) mit Tests gruen

In allen anderen Faellen: offen lassen, Robert entscheidet.

---

## Tests-Pflicht im selben PR

Kein "Tests folgen morgen". Ausnahmen muessen im PR-Comment begruendet und in einem direkt verlinkten Follow-up-Issue geplant sein.

Pflicht pro PR:
- Unit-Tests fuer jede neue Funktion
- Integrationstest fuer jeden neuen Endpoint
- Adversarial-Tests fuer jeden LLM-Touchpoint mit User-Input
- Bei Frontend-Aenderungen: Subagent-UI-Test via Browser-Use CLI 2.0

---

## Frontend-Build auf Host (Constraint #3 + #4)

**Immer auf dem Host, nie im Docker** (Proxmox-LXC-Limit):

```bash
cd /opt/content-autopilot-v2/frontend
npm run build
```

Frontend-Changes benoetigen immer eine passende Backend-Aenderung im selben PR (oder direkt verlinktem PR). Kein Backend-only-PR ohne Frontend-Anbindung wenn ein neuer Endpoint gebaut wird.

---

## Mobile-First (Constraint #13)

Primaerer User-Touchpoint ist der Telegram-Bot, nicht das Web-Dashboard. Bei jeder UX-Entscheidung zuerst fragen: "Was muss im Bot funktionieren?"

Frontend-Anforderungen:
- Touch-Targets mindestens 44x44 px
- Responsive ab 375 px Breite
- Loading + Error-States explizit
- Disabled-State wenn Pre-Conditions nicht erfuellt
- Keyboard-Accessibility (Tab + Enter)

---

## MD-Files via PromptLoader (Constraint #2)

Prompt-MDs (P01, P03, P04, P08, P12, P12b etc.) werden **ausschliesslich** ueber `PromptLoader` geladen. Kein Inline-Reproduzieren von Prompt-Texten im Code. Kein "verbessern" oder "vereinfachen" der Prompt-MDs durch Knecht.

---

## Skills-Manifest fuer Agents

implementer, reviewer und tester laden ihre Pflicht-Skills via `~/.claude/agents/skills-manifest.md`. Nicht manuell injizieren.

---

## Weiterfuehrende Dokumente

- [CLAUDE-PHASE2-CONSTRAINTS.md](CLAUDE-PHASE2-CONSTRAINTS.md) — vollstaendige Constraint-Liste
- [docs/RESTORE.md](docs/RESTORE.md) — Migration-Rollback und Backup-Restore
- [docs/adr/](docs/adr/) — Architektur-Entscheidungen (ADR-0001 bis ADR-0005)
- [docs/runbooks/](docs/runbooks/) — Betriebs-Runbooks
