# SPRINT-STATE — autonomer Architekt-Lauf (kiln crash-safe)

> **Zweck:** Driftfreie Wiederaufnahme nach Kontext-Kompaktierung oder Neustart. Diese Datei ist die *single source of truth* für den laufenden autonomen Lauf. **Erste Aktion bei Wiederaufnahme:** diese Datei lesen → `git log --oneline -8` → letzten offenen Punkt fortsetzen.
> **Leuchtturm:** `docs/REPORT-Content-Autopilot-v2.md` + `docs/report-content-autopilot-v2.html`. Bei Unsicherheit: `docs/FIGMA-SOLL-IST-MASTER.md` (= Board = single source of truth).

## Rollen & Tier-Routing (verbindlich)
- **Architekt (ich):** großer Überblick, Wiring/Design, arch/* Branch, kein Selbst-Merge nach main.
- **Tier:** fable = Sprint-Planung + Security-Review (Sprint-Ende) · opus = mittelkomplex · sonnet = daily-Impl · haiku = Kleinkram + Doku.
- **Cross-Model-Regel:** Reviewer-Modell ≠ Implementer-Modell. Review-Tier = fable/opus.
- **Knecht-Revier (NICHT anfassen):** Server/CI/Secrets/Deploy + Test-Serie #20, #32, #33, #34, #47, #48–#52, #24, #27. Koordination nur über GH-Issues.

## Harte Regeln
- TDD (RED→GREEN→REFACTOR), mocked Seams (lokaler venv Py3.9 ohne sqlalchemy → nur dep-freie Tests; voller E2E = Knecht/CI).
- Test-Befehl: `cd backend && PYTHONPATH=. ../../.venv/bin/python -m pytest <datei> -q`
- Nach jedem fertigen + (mock-)getesteten Punkt: Gate-Orakel → **commit [arch] + Co-Author Opus → push** (Knecht kann dann server-seitig testen).
- LLM-Policy: nur Requesty-Seam (`call_pipeline_llm`, Tier S1–S6, EU). Keine Modell-Literale, kein direktes SDK.
- E-Gate rot / neue DB-Tabelle / Provider-Wechsel / Merge → **STOPP, in ROBERT-BACKLOG.md eintragen**, nicht selbst entscheiden.
- Ehrlichkeit: „lokal mock-belegt" ≠ „Server-E2E belegt". Nie Status aufweichen.

## Branch-Lage
- Arbeits-Branch: `arch/weekloop` (rolling). Remote vorhanden. PR #55 offen (#15+#16+#43-Konzept+Reports) — Robert-Merge ausstehend.
- Push-Ziel: `arch/weekloop` (Knecht checkt das aus zum Testen).

---

## SPRINT 1 — „Phase A schließen + Compliance-Härtung"
Ziel: Telegram-Konversationsschleife vollständig (Antwort→Folgefrage→Post im Chat) + EU-Souveränität gehärtet. Alles Architekt-Revier, kein Robert nötig für den Code.

| # | Issue | Titel | Tier | Dep | Status |
|---|---|---|---|---|---|
| S1.1 | #17 | Folgefrage/Abschluss per Telegram zurück + Limit 2–3 | sonnet | #16 ✅ | ☐ offen |
| S1.2 | #18 | Idempotenz gegen Doppel-Verarbeitung (update_id-Dedupe) | sonnet | #16 | ☐ offen |
| S1.3 | #19 | [BLOCKER] Post-Generierung an Session-Abschluss + Post im Chat (M24-Kern-Gap) | opus | #17 | ☐ offen |
| S1.4 | #46 | Letzte Seam-Bypässe (voice_drift/md_converter/sensitive_detector) auf EU-Router | sonnet | — | ☐ offen |
| S1.5 | #22 | P17 lädt mit leerem System-Prompt (Heading-Fix) | sonnet | — | ☐ offen |
| S1.6 | #30 | Modell-Pinning: -latest-Modelle pinnen oder Policy-Ausnahme | haiku | — | ☐ offen |
| S1.7 | #56 | #16-Followup: routed_to in telegram_message_log persistieren | sonnet | #16 ✅ | ☐ offen |
| S1.8 | #57 | #16-Followup: targeted-Sessions mode-Filter | sonnet | #16 ✅ | ☐ offen |
| S1.9 | — | Security-Review (fable) + Gate-Orakel über den ganzen Sprint | fable | alle | ☐ offen |

**Aktueller Fokus:** Sprint-1-Detailplan (fable) wird erstellt; #46 läuft parallel.
**Nächste Aktion:** fable-Plan abwarten → S1.1 (#17) starten.

### Backlog danach (Sprint 2+, Reihenfolge vorläufig)
- Sprint 2 „Setup-Schema": #43-Impl (DB-Migration → Robert!), #29/#25/#26 Schema, #44 Wizard 6→8.
- Sprint 3 „Board-Vervollständigung": #35 P07-Push, #36 Intent-Routing, #37 Feedback-Loop, #41 P17-Ausrichtung, #38 Quality-Gate, #39 P02, #40 Voice-Fallback.

---

## LOG (jüngste zuerst)
- 2026-06-12 — Sprint-1 aufgesetzt, durable State + Robert-Backlog angelegt. #15/#16/#43-Konzept in PR #55. fable-Plan + #46 angestoßen.
