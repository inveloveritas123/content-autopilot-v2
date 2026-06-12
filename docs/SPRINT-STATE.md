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

### GitHub-Sprint-Struktur (angelegt)
- Milestones 1/2/3 = Sprint 1/2/3; alle Issues zugeordnet.
- **Master-Tracking-Issue #59** = detaillierter Fahrplan Architekt+Knecht (Reihenfolge, Deps, Akzeptanz, Robert-Entscheide).

---

## BOOTSTRAP (bei Wiederaufnahme — z.B. nach Limit-Reset/Kompaktierung)
1. Diese Datei lesen → `git -C content-autopilot-v2 log --oneline -10` (Stand prüfen).
2. Branch `arch/weekloop`. Test-Sanity (sollte grün sein): `cd content-autopilot-v2/backend && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_idempotency_routing.py tests/test_telegram_inbound_routing.py tests/test_p08_service.py tests/test_session_post_task.py tests/test_eu_router_migration.py tests/test_pipeline_llm.py tests/test_layer1_extraction.py -q` → 138 passed erwartet.
3. **Subagenten verfügbar?** (Session-Limit-Reset 22:30 Europe/Berlin). Wenn ja → Sprint 2 bauen; wenn nein → Hauptloop-eigene, kleine, sichere Items oder erneut warten.
4. Sprint-2-Plan: fable Detailplan je Issue gegen den Code (wie SPRINT-1-PLAN.md), dann sonnet/opus-Impl mit TDD + geteiltem Test-Helper `tests/_telegram_task_env.py` (Anti-Pollution!), Gate-Orakel, push, Issue kommentieren.

### Sprint 2 — Reihenfolge & autonom-Machbarkeit
| Issue | Tier | autonom jetzt? | Hinweis |
|---|---|---|---|
| #44 Wizard 6→8 Phasen | sonnet | ✅ Struktur (Fragen-Content später Chris) | self-contained in `api/wizard.py:WIZARD_PHASES`; Board 2.2 listet die 8 Phasen |
| #43 Werte-Entität | fable→sonnet | ⚠️ Code ja, **Migration→Robert** | Konzept `docs/CONCEPT-43-werte-entitaet.md`; Tabelle `tenant_customer_values` NICHT auf Prod anwenden |
| #29 Schema-Konsumenten | opus | ⚠️ besser nach #33-Merge | gradual rewire; ohne echte Schema-Läufe riskant |
| #25/#26 Alt-Rows/_meta | sonnet | ⚠️ dep #29 | |
| #30 Modell-Pinning | haiku | ⚠️ vorsichtig | -latest pinnen ändert Verhalten → eher Policy-Ausnahme dokumentieren |
| #33/#32/#34/#47/#48/#49 | knecht | ❌ Knecht-Revier | nicht anfassen |

**Empfohlener erster Sprint-2-Schritt nach Reset:** fable-Detailplan #44 + #43 → #44 sonnet bauen (sicher, board-anchored) → #43 Code+Migration vorlegen (Robert-Flag).

### Sprint-2-Fortschritt
- ✅ **#44 Wizard 6→8 Phasen fertig** — `api/wizard_phases.py` (dep-frei extrahiert), 8 Board-Phasen in Reihenfolge, hardcoded „6" entfernt; 101 Tests grün. Fragen-Wortlaut der neuen Phasen = Chris-Flag (board-konforme Defaults).
- 📋 **#43-Detailplan fertig** (`docs/SPRINT-2-PLAN-43.md`): Tabelle `tenant_customer_values` (Migration **053**, Robert-Freigabe), P12-Eingriff `p12_task.py:83-114`+`:333-339`, P17-Vorbau `brand_voice.py:759-899`. Atomare Schritte: 1) Schema+Resolver (sonnet, Review opus) → 2) Backfill → 3) P12-Injektion → 4) P17-decide-generisch.
- ✅ **#43 Schritt 1 fertig**: Migration 053 (`tenant_customer_values`, down_revision=049, freigabe-robert, NICHT angewandt) + canonical_profiles TABLE_MAP/Resolver/Regex + schema_transformer. 29 Tests + 115 Anti-Pollution grün. Pre-existing Py3.9-Bug in canonical_profiles mitgefixt. Robert-Flag in ROBERT-BACKLOG.
- ✅ **#43 Schritt 3 fertig**: P12-Injektion — `_load_active_profiles` → 4-Tupel inkl. customer_values, fail-open. `VALUES_KEYS_FOR_P12`-Whitelist.
- ✅ **#43 Schritt 2 fertig**: `tasks/values_backfill_task.py` — idempotenter, tenant-gescopter Backfill aus memory_chunks 'werte' (+ Setup-Werte), source='memory_promotion', fail-open (Tabelle fehlt → no_op).
- ✅ **#43 Schritt 4 fertig**: P17-Vorbau — `brand_voice.py` decide_drift_observation entitäts-generisch (`entity_type` → Zieltabelle via `brand_voice_drift_helpers._ENTITY_TABLE`), neue `op:"append"`-Operation für Listen-Felder (werte[]); voice-Pfad 100% rückwärtskompatibel (COALESCE entity_type='voice'). Schreibziel für #41 steht.
- ✅ **#43 KOMPLETT** — Board-Trias Voice/WERTE/Avatar hergestellt (Schema+Resolver+P12-Injektion+Backfill+P17-Ziel). Volle Wirkung nach Migration 053 (Robert) + Backfill-Lauf (Knecht). Test-Infra durabel saniert: **307 Stub-Tests reihenfolge-unabhängig grün** über 14 Suiten.
### Sprint 3 (begonnen)
- ✅ **#35 P07-Research-Push fertig**: `p07_research_task` sendet neue Findings + Hooks pro Tenant in den Chat (`_resolve_chat_id`+`_send_telegram_message`), idempotent (natürlich über bestehenden source_item_id-SELECT, keine Migration), E3-gescopet, fail-open. 21 Tests, 301 Anti-Pollution grün. Bahn 4 Pfad A geschlossen.
- ✅ **#40 Voice-Fallback fertig**: bei fehlender Stimmquelle generiert P03 ein kanonisches Voice-Profil aus Kontext+Avatar über den EU-Seam (VOICE_FALLBACK→S6), Fallback-Provenance, fail-open. 26 Tests grün.

### ⚠️ Branch-Koordination (NEU, 2026-06-13)
**Knecht arbeitet jetzt AKTIV auf `arch/weekloop`** (Commit 29e4b1c: ruff/eslint/yaml + Test-Collection-Pollution-Fixes). → **vor jedem Push `git fetch` + rebase** (nicht force-pushen). Arbeitsteilung: Architekt = Features (per-File-TDD grün), Knecht = CI-Grünung auf echter Py3.11-Umgebung.
**Py3.9-Realität:** Lokaler venv = Py3.9; Code zielt auf Py3.11/3.12. Module mit `datetime.UTC` u.ä. sind lokal NICHT importierbar → kombinierte lokale Läufe können Collection-Errors zeigen, die in CI (Py3.11+) NICHT existieren. **Verifikations-Bar: Einzeldatei grün + per-File-Anti-Pollution; volle kombinierte Suite = CI (Knecht).**

### Nächste Architekt-Items (alle per-File-TDD, dann fetch+rebase+push)
- #37 Feedback-Loop „nochmal anders" (opus, dep #19✅) · #38 Quality-Gate (opus) · #36 Intent-Routing P09/P13 (opus, dep #16✅) · #41 P17-Beobachter (fable, dep #43✅, jetzt entblockt) · #22 P17-Prompt (sonnet).
- Sprint-2-Rest #29/#25/#26 (Schema) besser nach #33-Merge (Knecht).

---

## LOG (jüngste zuerst)
- 2026-06-12 — **S1.2/S1.7/S1.8 (#18/#56/#57) fertig**: Idempotenz 2-Schicht (routed_to-Guard in _route_inbound_message + update_id-Dedupe in _store_and_dispatch), persist_routing_decision verdrahtet, targeted-mode-Filter. Test-Infra durabel saniert: gemeinsamer `tests/_telegram_task_env.py` (eine geteilte tasks.telegram_task-Instanz) → 112 Stub-Tests reihenfolge-unabhängig grün. Optionaler update_id-Unique-Index → ROBERT-BACKLOG (nicht blockierend).
- 2026-06-12 — **S1.4 #46 fertig**: 3 US-Anthropic-Calls auf EU-Seam (voice_drift→S6 gleiches Modell EU; md_converter/sensitive_detector→S2 mistral-EU). Test-Pollution (eu_router stubte services.pipeline_llm) in 2 Iterationen sauber gefixt → 99 Stub-Tests reihenfolge-unabhängig grün. sensitive_detector-Modellwahl → ROBERT-BACKLOG.
- 2026-06-12 — Sprint-1-Detailplan (fable) in `docs/SPRINT-1-PLAN.md`: Bau-Reihenfolge #18→#17→#19, keine zwingende DB-Migration.
- 2026-06-12 — Sprint-1 aufgesetzt, durable State + Robert-Backlog angelegt. #15/#16/#43-Konzept in PR #55. fable-Plan + #46 angestoßen.
