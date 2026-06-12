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
| S1.1 | #17 | Folgefrage/Abschluss per Telegram zurück + Limit 2–3 | sonnet | #16 ✅ | ✅ fertig (Send via _send_telegram_message, Limit 5→3) |
| S1.2 | #18 | Idempotenz gegen Doppel-Verarbeitung (update_id-Dedupe) | sonnet | #16 | ✅ fertig (2-Schicht: routed_to-Guard + update_id-Dedupe) |
| S1.3 | #19 | [BLOCKER] Post-Generierung an Session-Abschluss + Post im Chat (M24-Kern-Gap) | opus | #17 | ✅ fertig (session_post_task, P12→P12b→Chat, 3-fach idempotent, E3-Scope) |
| S1.4 | #46 | Letzte Seam-Bypässe (voice_drift/md_converter/sensitive_detector) auf EU-Router | sonnet | — | ✅ fertig (lokal 99 Tests grün; sensitive_detector-Modellwahl → Robert) |
| S1.5 | #22 | P17 lädt mit leerem System-Prompt (Heading-Fix) | sonnet | — | ☐ offen |
| S1.6 | #30 | Modell-Pinning: -latest-Modelle pinnen oder Policy-Ausnahme | haiku | — | ☐ offen |
| S1.7 | #56 | #16-Followup: routed_to in telegram_message_log persistieren | sonnet | #16 ✅ | ✅ fertig (mit #18 gebündelt) |
| S1.8 | #57 | #16-Followup: targeted-Sessions mode-Filter | sonnet | #16 ✅ | ✅ fertig (mit #18 gebündelt) |
| S1.9 | — | Security-Review + Gate-Orakel über den ganzen Sprint | fable→Architekt | alle | ✅ GRÜN (`docs/SPRINT-1-SECURITY-REVIEW.md`; fable-Pass nachzuholen nach Limit-Reset) |

**✅ SPRINT 1 ABGESCHLOSSEN** — Telegram-Konversationsschleife vollständig (Antwort→Folgefrage→**Post im Chat**, M24-Kern-Gap geschlossen) + EU-Souveränität gehärtet (#46). Alle auf `arch/weekloop`, PR #55. Server-E2E = Knecht.
**Nächste Aktion:** Sprint 2 (Setup/Schema) detailliert planen → bauen. Subagenten erst nach Session-Limit-Reset 22:30 Europe/Berlin verfügbar.

### Backlog danach (Sprint 2+, Reihenfolge vorläufig)
- Sprint 2 „Setup-Schema": #43-Impl (DB-Migration → Robert!), #29/#25/#26 Schema, #44 Wizard 6→8.
- Sprint 3 „Board-Vervollständigung": #35 P07-Push, #36 Intent-Routing, #37 Feedback-Loop, #41 P17-Ausrichtung, #38 Quality-Gate, #39 P02, #40 Voice-Fallback.

---

## LOG (jüngste zuerst)
- 2026-06-12 — **S1.2/S1.7/S1.8 (#18/#56/#57) fertig**: Idempotenz 2-Schicht (routed_to-Guard in _route_inbound_message + update_id-Dedupe in _store_and_dispatch), persist_routing_decision verdrahtet, targeted-mode-Filter. Test-Infra durabel saniert: gemeinsamer `tests/_telegram_task_env.py` (eine geteilte tasks.telegram_task-Instanz) → 112 Stub-Tests reihenfolge-unabhängig grün. Optionaler update_id-Unique-Index → ROBERT-BACKLOG (nicht blockierend).
- 2026-06-12 — **S1.4 #46 fertig**: 3 US-Anthropic-Calls auf EU-Seam (voice_drift→S6 gleiches Modell EU; md_converter/sensitive_detector→S2 mistral-EU). Test-Pollution (eu_router stubte services.pipeline_llm) in 2 Iterationen sauber gefixt → 99 Stub-Tests reihenfolge-unabhängig grün. sensitive_detector-Modellwahl → ROBERT-BACKLOG.
- 2026-06-12 — Sprint-1-Detailplan (fable) in `docs/SPRINT-1-PLAN.md`: Bau-Reihenfolge #18→#17→#19, keine zwingende DB-Migration.
- 2026-06-12 — Sprint-1 aufgesetzt, durable State + Robert-Backlog angelegt. #15/#16/#43-Konzept in PR #55. fable-Plan + #46 angestoßen.
