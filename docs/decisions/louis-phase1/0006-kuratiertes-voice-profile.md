> Übernommen aus Louis' Phase-1-Übergabe (2026-05-29). Möglicherweise durch v2 überholt — siehe Schema-Realignment.

# ADR 0006 — Kuratiertes Voice-Profile statt flat-Merge von p01/p03/p04

**Datum:** 2026-05-26
**Status:** Akzeptiert
**Entschieden von:** Louis (mit Claude)
**Bezogen auf:** ADR 0001 (Schema-First, Stack-Last), ADR 0002 (Tenant-Wrapper), ADR 0005 (Iststand-vs-Zielbild)

## Kontext

P01 → P03 → P04 erzeugen drei JSONs pro Kunde (~49 kB zusammen für Eric). Nachgelagerte Prompts (P07–P17, ohne P11/P14) konsumieren Teile davon. Frage: Bauen wir aus den drei JSONs ein gemergtes `voice_profile.json`, das als kanonischer Konsum-Vertrag dient — und wenn ja, flach oder kuratiert?

Drei Optionen lagen vor:

1. **Kein Merge.** Jeder nachgelagerte Prompt liest selbst aus p01/p03/p04. Kein neuer Vertrag, aber Konsumenten kennen die Quellstruktur direkt — Migration bei Schema-Änderungen wird teuer.
2. **Flat-Merge.** Alle drei JSONs in ein Objekt zusammen. Einfach, aber: ~63 % der Felder werden downstream nicht direkt konsumiert (P03/P04 haben sie schon destilliert), Naming-Kollisionen (`_meta`, `referenz_saetze`), und P12 zahlt die volle Größe pro Post-Generierung.
3. **Kuratierter Merge mit Layern.** Felder nach tatsächlicher Downstream-Nutzung gruppieren, ungenutzte Felder rauslassen.

Feldnutzungs-Analyse aller Konsumenten-Prompts:
- ~12 Felder werden von ≥3 Konsumenten gelesen (z.B. `grundton.charakterisierung`, `referenz_saetze.original`, `vermeidungsprofil`, `content_trigger.scroll_stopper`)
- ~18 Felder von 1–2 Konsumenten (P12-Spezialfelder wie `satzarchitektur`, `wortschatz`)
- ~50 Felder von keinem Konsumenten direkt (z.B. `zielkunde.*`, `angebot.*`, `markt.*`, `innenwelt.*`, `wunschbild.*` — alle bereits durch P03/P04 destilliert)

## Entscheidung

**Option 3 — kuratiertes `voice_profile.json` mit 3 Layern + optionalem Bias-Block.**

```
voice_profile.json
├── _meta                     Tenant-Wrapper, merge_version, Quellen-Audit
├── _iststand_vs_zielbild     aus p01 durchgereicht (optional, siehe ADR-0005)
├── kern                      ~8 kB. IMMER injizieren.
│   ├── person                name, branche, teamgroesse, standort, differenzierung, du_oder_sie
│   ├── voice                 grundton, referenz_saetze_original, vermeidungsprofil,
│   │                         pointen_stil, verletzlichkeit_level, stance
│   └── avatar                rolle_und_alltag, scroll_stopper, resonanz_saetze, abstoss_trigger
├── voice_detail              ~12 kB. NUR für P12 / P12b / P13.
│                             satzarchitektur, wortschatz vollständig, erzaehlmuster,
│                             emotionaler_ausdruck, emotionaler_subtext, ueberzeugungsstil,
│                             zielgruppen_sprachfilter, referenz_saetze_adaptiert
└── avatar_detail             ~6 kB. NUR für P09 / P12.
                              alltagsszenen, sprache_der_zielgruppe, vertrauens_trigger,
                              content_reservoir (starke_meinungen, wiederkehrende_themen)
```

Nicht enthalten (bei Bedarf direkt aus Quell-JSONs lesen): `p01.zielkunde`, `p01.angebot`, `p01.markt`, `p01.vertrauen`, `p01.person.gruendungsgeschichte/antrieb/tagesablauf/fehler_und_learnings`, `p01.sprache.fachbegriffe`, `p04.innenwelt`, `p04.wunschbild`, `p04.blockaden`, `p04.ausloesemoment`, `p04.alltagsszenen.wiederkehrende_muster`, `p04.avatar_basis`.

**Schema:** `schemas/voice_profile.schema.json` (Top-Level strict, Subobjekte tolerant wegen Pass-Through-Pflicht aus p03/p04).
**Runner:** `scripts/merge-voice-profile.ts` — reine Datentransformation, kein LLM-Call, kein API-Cost.
**Versionierung:** `_meta.merge_version` (`merge-v1.0` initial). Bei Strukturänderung Version hochziehen.
**Bricht-bei-Fehlen-Regel:** Wenn p01/p03/p04 fehlen → klarer Abbruch. Kein Partial-Merge — ein halbes voice_profile ist für P12 unbrauchbar.

## Warum nicht Option 1 (kein Merge)

- Jeder Konsumenten-Prompt müsste sein eigenes Feld-Mapping pflegen. Schema-Drift in p01/p03/p04 würde an N Stellen brechen statt an einer.
- Kein zentraler Ort, an dem `_iststand_vs_zielbild` für alle Konsumenten sichtbar ist.

## Warum nicht Option 2 (flat-Merge)

Gemessen an Erics Daten:
- Flat-Merge wäre **~49 kB** (alle drei JSONs zusammen).
- Voice-Profile ist **~28 kB total**, davon **kern allein ~8 kB**.
- Für schlanke Prompts (P08/P10/P16) die nur `kern` brauchen: **~83 % kleiner** als flat-Merge.
- Für P12 (voll: kern + voice_detail + avatar_detail): **~42 % kleiner**.

Plus: Naming-Kollisionen (`_meta` × 3, `referenz_saetze` p03/p04, `identitaet` nur p04 — Konflikt-Potenzial bei künftigen Schema-Änderungen).

## Konsequenzen

**Positiv:**
- Eine Schema-Datei (`voice_profile.schema.json`) ist der Vertrag für alle Konsumenten. P07–P17-Runner müssen p01/p03/p04 nicht mehr direkt kennen.
- Kostenersparnis ist messbar (~42 % auf P12, ~83 % auf schlanken Prompts) ohne Qualitätsverlust — alle ≥1-Konsumenten-Felder sind enthalten.
- `_iststand_vs_zielbild` wird zentral durchgereicht, kein Konsument muss in p01 separat schauen.
- Pro-Konsumenten-Helper (in einem späteren ADR/Implementierungsschritt: `selectForP12()`, `selectForP08()` etc.) können das Profile auf das Minimum reduzieren, das der jeweilige Prompt braucht.

**Negativ:**
- Zusätzlicher Pipeline-Schritt nach P04 (`npm run merge`). Vergisst man ihn, läuft P09/P12 mit veralteten Daten — sichtbar an `_meta.sources.*.generation_id`.
- Wenn ein neuer Konsumenten-Prompt ein Feld braucht, das aktuell im Archive ist, muss das Schema/Merger ergänzt werden (+ Version hoch). Erwartet selten.
- Für Audit-Fälle (z.B. „warum hat P12 das so geschrieben") muss man neben voice_profile auch in die Quell-JSONs schauen.

## Konsumenten-Erwartung (nicht-bindend, Implementierung folgt)

| Prompt | Konsumiert |
|---|---|
| P07 (Themen-Research) | `kern` |
| P08 (Fragen-Konversation) | `kern` |
| P09 (Content-Ideen) | `kern` + `avatar_detail` |
| P10 (Content-Kern) | `kern` |
| P12 (Post-Generierung) | `kern` + `voice_detail` + `avatar_detail` + `_iststand_vs_zielbild` |
| P12b (Post-Optimierung) | `kern` + `voice_detail` |
| P13 (Hook-Varianten) | `kern` + `voice_detail` |
| P15 (Eigene Idee) | `kern` + `_iststand_vs_zielbild` |
| P16 (Post-Überarbeitung) | `kern` + `voice_detail` |
| P17 (Kontext-Update) | direkt p01/p03/p04 lesen, nicht voice_profile |

## Trigger für Re-Entscheidung

- Wenn der Anteil archivierter (= ungenutzter) Felder unter 30 % fällt — dann ist die Kuratierung nicht mehr lohnend, flat-Merge reicht.
- Wenn ein neuer Konsument viele Archive-Felder braucht — dann Schema-Erweiterung statt Workaround.
- Migration zu SaaS (Phase 2): voice_profile-Erzeugung wandert in einen Post-P04-Hook in der DB-Pipeline, das Schema bleibt der Konsumenten-Vertrag.
