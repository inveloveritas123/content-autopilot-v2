#!/usr/bin/env python3
"""G-VOICE-GOLDEN: Voice-Golden-Set-Eval-Gate fuer den content-autopilot.

Macht "die Voice-Stimme passt" zu einer pruefbaren Zahl. Faehrt die
synthetischen Voice-Golden-Profile (tests/fixtures/voice_golden/*.json) durch
den regelbasierten Voice-Consistency-Judge (services.voice_gate.
check_voice_consistency) und prueft, ob jeder Fall korrekt klassifiziert wird:
good_posts muessen passed=True liefern, bad_posts muessen passed=False liefern.

Anders als das Avi-Eval-Gate (Vorbild, Leitivo) braucht dieses Gate KEINEN
Live-LLM-Proxy — der Voice-Judge ist reine stdlib-Regellogik (MATTR/
Satzlaenge-Korridore, Anti-KI-Blocklist, Verbotsphrasen). Es gibt deshalb auch
keinen "ohne Proxy-Key nur Teilpruefung"-Modus wie bei Avi: dieses Gate laeuft
IMMER voll und deterministisch, in jeder CI (kein Skip-Pfad).

Exit-Code:
  0 — alle Golden-Cases korrekt klassifiziert (oder keine Fixtures gefunden,
      analog zum Avi-Gate: "nichts zu pruefen" blockt nicht).
  1 — mindestens ein Fall falsch klassifiziert (Fehlklassifikations-Liste auf
      stdout).

Nutzung:
    cd backend
    PYTHONPATH=. .venv/bin/python scripts/check_voice_golden_gate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

GATE_VERSION = "1.0.0"

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_FIXTURES_DIR = _BACKEND_ROOT / "tests" / "fixtures" / "voice_golden"


def _load_profiles(fixtures_dir: Path) -> list[dict]:
    profiles = []
    for path in sorted(fixtures_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"  WARNUNG: {path.name} konnte nicht geladen werden: {e}")
            continue
        data["_source_file"] = path.name
        profiles.append(data)
    return profiles


def _evaluate() -> int:
    sys.path.insert(0, str(_BACKEND_ROOT))
    from services.voice_gate import check_voice_consistency

    profiles = _load_profiles(_FIXTURES_DIR)
    print(
        f"G-VOICE-GOLDEN v{GATE_VERSION} — Voice-Golden-Set-Gate (regelbasiert, kein Live-Proxy noetig)"
    )

    if not profiles:
        print(f"  keine Golden-Profile gefunden unter {_FIXTURES_DIR} — nichts zu pruefen (OK).")
        return 0

    total_good = 0
    total_bad = 0
    misclassified: list[str] = []

    for profile in profiles:
        key = profile.get("profile_key", profile["_source_file"])
        voice_profile = profile.get("profile", {})
        good_posts = profile.get("good_posts", [])
        bad_posts = profile.get("bad_posts", [])

        good_ok = 0
        for post in good_posts:
            total_good += 1
            result = check_voice_consistency(post.get("text", ""), voice_profile)
            if result["passed"]:
                good_ok += 1
            else:
                misclassified.append(
                    f"{key}/{post.get('id', '?')}: erwartet passed=True (good_post), "
                    f"bekam passed=False — violations: {result['violations']}"
                )

        bad_ok = 0
        for post in bad_posts:
            total_bad += 1
            result = check_voice_consistency(post.get("text", ""), voice_profile)
            if not result["passed"]:
                bad_ok += 1
            else:
                misclassified.append(
                    f"{key}/{post.get('id', '?')}: erwartet passed=False (bad_post), "
                    f"bekam passed=True (Score {result['score']}) — kein Verstoss erkannt"
                )

        print(f"  [{key}] good={good_ok}/{len(good_posts)} bad_erkannt={bad_ok}/{len(bad_posts)}")

    total_cases = total_good + total_bad
    correct = total_cases - len(misclassified)
    print(
        f"G-VOICE-GOLDEN: {correct}/{total_cases} Golden-Cases korrekt klassifiziert "
        f"({len(profiles)} Profil(e), {total_good} good_posts, {total_bad} bad_posts)."
    )

    if not misclassified:
        print("G-VOICE-GOLDEN: OK.")
        return 0

    print(f"G-VOICE-GOLDEN: {len(misclassified)} Fehlklassifikation(en):")
    for m in misclassified:
        print(f"  - {m}")
    print(
        "REMEDIATION: Golden-Fixture pruefen (tests/fixtures/voice_golden/*.json) — "
        "ist der good_post wirklich sauber? Verletzt der bad_post wirklich Anti-KI-Blocklist/"
        "verbotene Phrasen? Oder hat sich services/voice_gate.py geaendert (Regressionsverdacht)?"
    )
    return 1


def main() -> int:
    try:
        return _evaluate()
    except Exception as e:
        print(f"G-VOICE-GOLDEN v{GATE_VERSION}: Gate konnte nicht laufen: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
