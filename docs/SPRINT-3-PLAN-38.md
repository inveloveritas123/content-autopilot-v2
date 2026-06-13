# Sprint-3-Plan #38 — Quality-Gate vom Stub zum echten Scorer (Final-Gate, Bahn 5)

> Detailplan gegen den realen Code. Opus-Tier, **berührt den Versandpfad** (outward) → in Chunks bauen,
> Oracle-getrieben (F1 gegen echten Korpus). Verification-first: keine Assertion aufweichen.

## SOLL vs. IST
- **SOLL:** Steuerbare Qualität als **Final-Gate vor dem Telegram-Versand** des generierten Posts (Bahn 5).
- **IST:** `services/quality_gate_stub.py` = Stub (`score = len/10` + Heuristik-Violations), **F1 ~0.27**.
  Nur in `api/eval.py` (Dashboard) verdrahtet — **nicht** im Versandpfad.

## Oracle (verifiziert vorhanden)
- Harness `backend/eval/run_quality_gate_eval.py`: lädt `eval/quality_gate_corpus/<branche>/labeled_posts.yaml`
  (4 Branchen: handwerk/recht/finanzen/_generic, je ~20 gelabelte Posts), ruft `quality_gate_check()`,
  rechnet Confusion-Matrix + Precision/Recall/F1 + ROC-AUC über Thresholds, schreibt `eval_results/quality_gate_*.json`.
  **CI-Gate `--min-f1`** schon vorgesehen. Harness **file-importiert** den Scorer (umgeht `services/__init__`)
  → der getunte Scorer-Kern muss **dep-frei importierbar** bleiben.
- Lokaler Lauf des Harness scheitert nur an `datetime.UTC` (Py3.9) → **Test-seitig** F1 dep-frei nachrechnen
  (pyyaml ist im venv vorhanden) → lokales Py3.9-grünes Oracle, unabhängig vom Harness.

## Kontrakt (stabil halten)
`quality_gate_check(post_text: str, branche: str) -> {passed: bool, score: float(0..100),
violations: list[str], threshold: float, branche: str}` — Signatur **nicht** brechen (eval.py + Harness hängen dran).

## Chunks (klein → groß, jeder mit Oracle)
1. **Realer Struktur-/Regel-Scorer (dep-frei, $0)** — ersetzt `len/10`:
   Längen-Bänder, Caps-Ratio, Satzbau/CTA/Hashtag-Sanity, branchen-Disclaimer (recht/finanzen),
   PII-/Eigenname-/Ort-Heuristik (E2-nah). Thresholds pro Branche aus **`config/quality_standards/*.yml`**
   (neu anzulegen; Default-Set board-konform). **Akzeptanz: F1 deutlich > 0.27** (Ziel ≥ 0.6 als erster Schritt),
   gemessen via neuem dep-freien `tests/test_quality_gate_eval.py` (lädt Korpus, rechnet F1). Tuning gegen Korpus,
   **Assertions nie aufweichen** — wenn F1 nicht steigt, Logik fixen, nicht den Test.
2. **Semantische Schicht (LLM via EU-Seam, optional/injizierbar)** — Kohärenz/On-Brand/Board-Qualität als
   Zusatz-Score. **Nicht** im dep-frei-importierten Kern (sonst bricht der Harness-Import) → als separate Funktion,
   die der Versand-Task aufruft; cost-cap-gated; im **Testmodus billiges Modell** (Robert #42). Mock-getestet.
3. **Final-Gate-Wiring** in `tasks/session_post_task.py:generate_post_from_session` **vor Schritt 7**
   (`_send_telegram_message`, ~Z.255): `quality_gate_check` (+ optional semantisch) → bei `not passed`
   **nicht roh senden**, sondern in den bestehenden **Review-Queue-Pfad (#83, „geflaggt"-Zweig)** routen /
   halten / 1× Regenerate. fail-open für Verfügbarkeit, fail-closed für Qualität (konfigurierbar). E3/idempotent.

## Abhängigkeiten / Flags
- **Korpus-Qualität** (Label-Verteilung) = Oracle-Güte. Falls Labels dünn/schief → Chris/Robert-Flag (Daten).
- `config/quality_standards/*.yml` Default-Werte board-konform; Branchen-Schwellen ggf. Chris-Review.
- Versandpfad-Änderung (#83-Routing) = outward → vor Aktivierung Mensch bestätigen / hinter Flag.

## Nicht in #38
- Review-Queue-UI (#83 separat). Korpus-Erweiterung/Re-Labeling (eigener Daten-Task).
