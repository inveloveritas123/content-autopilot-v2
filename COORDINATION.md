# Koordination: Architekt ↔ Knecht (GitHub)

**Stand: 2026-06-12. Gitea ist stillgelegt — GitHub `inveloveritas123/content-autopilot-v2` ist die alleinige Source of Truth.**

## Rollen
| Rolle | Wo | Modell | Zuständigkeit |
|---|---|---|---|
| **Architekt** | Roberts Mac (Claude Code) | Opus/Fable | Wochenloop-Wiring (#15–#20), Schema-Architektur (#25/#26/#29/#43), Board-Lücken (#35–#44), Konzeption/Reviews, COORDINATION.md |
| **Knecht** | Server B (152.53.142.163, /opt/content-autopilot-v2) | Sonnet/Haiku | Server-Fixes, Deploy/Infra, CI-Hygiene, Secrets (#14/#21/#24/#34), praktisches Testen (#32, Telegram-E2E) |
| **Robert** | Mensch | — | Freigaben (DB-Migrationen, LLM-Config, Firewall, Merges nach main), Entscheidungen (#42) |

## Konventionen (verbindlich)
1. **Branches:** Architekt `arch/<thema>`, Knecht `knecht/<thema>`. NIE auf fremde Branches pushen. main nur per PR/konsolidiertem Merge.
2. **Commits:** Titel-Präfix `[arch]` bzw. `[knecht]`. Git-Author bleibt Robert; Unterscheidung über Präfix + Co-Author-Zeile (Architekt: Opus; Knecht: sein Modell).
3. **Issues:** Label `architekt`/`knecht` = Zuteilung. Vor jeder Aufgabe offene Issues mit eigenem Label lesen (`gh issue list --label <rolle> --state open`). GitHub pusht nichts — Pull-Prinzip.
4. **Revier-Schutz:** Dateien des jeweils anderen nur nach Issue-Absprache anfassen. Architekt-Revier aktuell: `backend/services/p08_service.py`, `layer1_extraction.py`, `backend/tasks/telegram_task.py`, `schema_transformer.py`, `canonical_wiring.py`, P09/P10/P12-Strecke. COORDINATION.md pflegt der Architekt.
5. **Pull before push, kleine PRs, CI grün vor PR.**
6. **LLM-Policy:** Alle Calls über den Requesty/LiteLLM-Router (Tiers S1–S6, EU-Modelle). Kein direktes SDK, keine Modell-Literale im Backend.

## Wo steht was
- Vision/SOLL: `docs/VISION-UND-PROJEKTPLAN.md` + `docs/FIGMA-SOLL-IST-MASTER.md` (maßgebliche Matrix)
- GitHub-Zustand: `docs/GH-SETUP-AUDIT.md` · Doc-Index: `docs/README.md`
- Fahrplan: Phase A Telegram-Loop (#15→#16/#17→#19→#18/#20) · Phase B Setup (#33→#32, Schema #29/#25/#26/#43) · Phase C Board-Lücken (#35–#41, #44) · Entscheid #42 (Robert)

## Aktueller Stand (2026-06-12)
- main `8e79b19`: PR #28 + Knecht-Greening + EU-Modelle + CI-Fixes (PR #31) konsolidiert. PR #28/#31 gemergt.
- `arch/weekloop`: #15 p08→Seam fertig (Tests grün), layer1 in Arbeit.
- CI: Lint grün (nach #31), E2E-Smoke rot bis NEXTCLOUD_PASSWORD-Secret (#34).
