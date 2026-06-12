# Session-Handoff B — 2026-06-12 (Abend)

> Folgt auf `HANDOFF-SESSION-2026-06-12.md` (Vormittag). Stand main `0b9f7df`, `arch/weekloop` `2be61e2`.
> Diese Session: Figma vollständig visuell analysiert (PDF 200dpi), Master-SOLL-IST, MVP-Plan mit ehrlicher
> Prozent-Rechnung, komplettes Backlog nach GitHub, Koordination Architekt↔Knecht etabliert, #15 fertig.

## Wo alles steht (Lese-Reihenfolge für neue Session)
1. `docs/MVP-PLAN.md` — **das Arbeitsdokument**: MVP-Definition (M1–M29), Bonus-Liste, Prozent-Rechnung, maschinenlesbares Backlog
2. `docs/FIGMA-SOLL-IST-MASTER.md` — maßgebliche Board-Matrix (visuelle Befunde!)
3. `COORDINATION.md` — Architekt↔Knecht-Konventionen (Branches, [arch]/[knecht], Labels, Revier)
4. `docs/VISION-UND-PROJEKTPLAN.md` — Vision + 5 Bahnen
5. `docs/GH-SETUP-AUDIT.md`, `docs/README.md` (Index)

## Die Zahlen (strenge Definition: nur echte Läufe = belegt)
**MVP 29 Elemente: 17 % belegt · 48 % gebaut (31 % davon nur theoretisch = Testlücke) · 52 % fehlt.**
Kern-Wahrheit: Bausteine ja, Workflow nein — kein Kunde könnte heute einen Post über das System erzeugen.
Das Herz (Chat-Antwort → Folgefrage → Post im Chat → Feedback) existiert nicht (#16/#17/#19/#37).

## Backlog-System (GitHub, vollständig)
33 offene Issues, alle gelabelt: Rolle (`architekt` 23 / `knecht` 10) · `mvp`(28)/`test`(7) ·
**`model:fable|opus|sonnet|haiku`** = empfohlenes Subagent-Modell. #42 = Robert-Entscheid (Modellwahl Content).
Abfrage: `gh issue list -R inveloveritas123/content-autopilot-v2 --label architekt --label mvp --state open`

## Branch-Lage
- **main** `0b9f7df`: konsolidiert (PR #28+#31 gemergt, EU-Modelle, CI-Fixes, alle Docs). CI: Lint grün, E2E-Smoke rot bis #34/#47 (NEXTCLOUD_PASSWORD).
- **arch/weekloop** `2be61e2`: **#15 KOMPLETT** (p08→S6/EU + layer1→S2 über `call_pipeline_llm`, 74+ Tests, Guards). Rebased auf main-Vorstand 8e79b19 — vor Weiterarbeit auf 0b9f7df rebasen (nur docs-Deltas, konfliktfrei). **Unmerged — Robert-Review/Merge offen.**
- **knecht/fix-33-json**: Knechts Fix für #33 (P01/P03 Markdown→JSON) mit Server-Repro. **Unmerged.**
- Knecht arbeitet auf Server B; sieht Aufgaben via Label-Poll (`--label knecht`), kein Auto-Push von GitHub.

## Architekt-Prioritäten (nächste Session, Phase A zuerst)
1. **#16 Inbound-Routing** (opus): `tasks/telegram_task.py` `_process_voice/_process_text` → bei aktiver bot_session
   die Kundenantwort an `p08_response()` routen statt nur memory_chunk. Revier: telegram_task.py, p08_service.py.
2. **#43 Werte-Entität Konzept** (fable, parallel — disjunkt): Werte-Speicher + P12-Injektion + P17-Schreibziel; an Schema-Zug #29/#25/#26 andocken.
3. **#17 Folgefrage/Abschluss zurück per Telegram** (sonnet, nach #16): Akzeptanz: max 2–3 Rückfragen (Board!).
4. **#19 Post am Session-Abschluss** (opus, nach #17): content_ideas 'ready_for_p10' → echter P10/P12/P12b-Lauf → Post in Chat.
5. Dann #18 (Idempotenz, sonnet), #20 (E2E, sonnet+Knecht), #36/#37 (opus).

## Knecht-Parallelspur (läuft unabhängig)
#33-PR mergen (nach Review) → #47 CI grün → #32 Eric-E2E wiederholen → Test-Serie #48–#52.

## Robert-Entscheide offen
- **#42** Content-Modell (Opus vs Sonnet-EU; Gemini-Remap der kreativen Pfade revidieren — dringender!)
- Merge-Freigaben: `arch/weekloop` (#15), `knecht/fix-33-json` (#33)
- #24 Deploy-Pfad (SSH vs self-hosted Runner) — mit Knecht

## Arbeitsweise (verbindlich, aus Memory)
WERKBANK-Loop (Konzeption→Impl→Kontrolle→Doku), TDD, Gate-Orakel vor PR. Subagenten gnadenlos parallel:
**fable**=hochanalytisch/lang · **opus**=mittelkomplex · **sonnet**=daily · **haiku**=doku. Nicht sofort Lösbares
→ SOFORT als GH-Issue. [arch]-Commit-Präfix + Opus-Co-Author. Kein Selbst-Merge nach main. LLM-Policy: nur
Requesty-Router (S1–S6, EU), keine Modell-Literale. Venv: `../.venv` (pytest; cwd=backend, PYTHONPATH=.).
