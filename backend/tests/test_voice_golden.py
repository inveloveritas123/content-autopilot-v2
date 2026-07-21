"""
test_voice_golden.py — Voice/Content-Golden-Set-Gate fuer services.voice_gate.

Doktrin (llm_foo/evals-testing): ein Golden-Set (30-100 Beispiele) muss in CI
verdrahtet UND NICHT skip-bar sein. Der bestehende test_golden_eric.py skippt
still, wenn die (untracked, PII-behaftete) Eric-Daten fehlen — gruene CI ohne
Aussagekraft ueber Voice-Qualitaet. Dieser Test schliesst die Luecke mit
SYNTHETISCHEN Golden-Profilen (tests/fixtures/voice_golden/*.json, fiktive
Personas, kein Kundenname/PII) und faehrt sie IMMER, deterministisch, ohne
Skip-Bedingung.

check_voice_consistency() (services/voice_gate.py) ist regelbasiert (MATTR/
Satzlaenge-Korridore, Anti-KI-Blocklist, explizite Verbotsphrasen) — kein LLM,
kein Netzwerk, kein DB-Zugriff. Deshalb ist dieser Test ein reiner
LLM-as-Judge-ERSATZ auf Regelbasis: good_posts muessen passed=True liefern
(Score 1.0, keine Verstoesse), bad_posts muessen passed=False liefern
(mindestens ein Verstoss — Anti-KI-Phrase und/oder verbotene Phrase).

    cd backend
    PYTHONPATH=. .venv/bin/python -m pytest tests/test_voice_golden.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.voice_gate import check_voice_consistency

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "voice_golden"


def _load_golden_profiles() -> list[dict]:
    """Laedt alle *.json-Golden-Profile aus tests/fixtures/voice_golden/.

    Sortiert nach Dateiname fuer stabile Testreihenfolge/-IDs. Wirft, wenn das
    Verzeichnis leer ist — ein leeres Golden-Set waere ein stiller Aussagekraft-
    Verlust genau wie ein Skip, das soll hier nicht unbemerkt passieren.
    """
    paths = sorted(FIXTURES_DIR.glob("*.json"))
    assert paths, f"Kein Voice-Golden-Profil gefunden unter {FIXTURES_DIR} — Golden-Set fehlt."
    profiles = []
    for p in paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        data["_source_file"] = p.name
        profiles.append(data)
    return profiles


GOLDEN_PROFILES = _load_golden_profiles()

# Params fuer die parametrisierten Tests: (profile_key, voice_profile, post_id, text).
_GOOD_CASES: list[tuple[str, dict, str, str]] = []
_BAD_CASES: list[tuple[str, dict, str, str]] = []
for _profile in GOLDEN_PROFILES:
    _key = _profile["profile_key"]
    _vp = _profile["profile"]
    for _post in _profile.get("good_posts", []):
        _GOOD_CASES.append((_key, _vp, _post["id"], _post["text"]))
    for _post in _profile.get("bad_posts", []):
        _BAD_CASES.append((_key, _vp, _post["id"], _post["text"]))

_GOOD_IDS = [f"{key}/{post_id}" for key, _, post_id, _ in _GOOD_CASES]
_BAD_IDS = [f"{key}/{post_id}" for key, _, post_id, _ in _BAD_CASES]


def test_golden_set_is_non_empty_and_has_minimum_size():
    """Sanity-Guard gegen ein leeres/zu kleines Golden-Set (stiller Aussagekraft-
    Verlust waere sonst moeglich, ohne dass ein Test das bemerkt)."""
    assert len(GOLDEN_PROFILES) >= 2, "mindestens 2 Golden-Profile erwartet"
    total_posts = len(_GOOD_CASES) + len(_BAD_CASES)
    assert total_posts >= 6, f"Golden-Set zu klein ({total_posts} Posts) fuer ein aussagekraeftiges Gate"


def test_golden_profiles_have_required_fields():
    """Struktur-Check: jedes Profil traegt profile_key/profile/good_posts/bad_posts,
    jeder Post hat id+text — verhindert ein stilles, halb-leeres Fixture."""
    for profile in GOLDEN_PROFILES:
        src = profile["_source_file"]
        assert profile.get("profile_key"), f"{src}: profile_key fehlt"
        assert isinstance(profile.get("profile"), dict), f"{src}: profile fehlt/kein dict"
        good = profile.get("good_posts") or []
        bad = profile.get("bad_posts") or []
        assert len(good) >= 2, f"{src}: mindestens 2 good_posts erwartet, hat {len(good)}"
        assert len(bad) >= 2, f"{src}: mindestens 2 bad_posts erwartet, hat {len(bad)}"
        for post in good + bad:
            assert post.get("id"), f"{src}: Post ohne id"
            assert post.get("text", "").strip(), f"{src}/{post.get('id')}: leerer Text"


@pytest.mark.parametrize("profile_key,voice_profile,post_id,text", _GOOD_CASES, ids=_GOOD_IDS)
def test_good_post_passes_voice_consistency(profile_key, voice_profile, post_id, text):
    """good_posts sind konstruiert, um zum Voice-Profil zu passen — der
    regelbasierte Judge muss sie ohne Verstoss durchwinken (Score 1.0)."""
    result = check_voice_consistency(text, voice_profile)
    assert result["passed"] is True, (
        f"[{profile_key}/{post_id}] sollte passed=True liefern, "
        f"Verstoesse: {result['violations']}"
    )
    assert result["violations"] == [], (
        f"[{profile_key}/{post_id}] hat unerwartete Verstoesse: {result['violations']}"
    )
    assert result["score"] >= 0.9, f"[{profile_key}/{post_id}] Score zu niedrig: {result['score']}"


@pytest.mark.parametrize("profile_key,voice_profile,post_id,text", _BAD_CASES, ids=_BAD_IDS)
def test_bad_post_fails_voice_consistency(profile_key, voice_profile, post_id, text):
    """bad_posts verletzen bewusst Anti-KI-Blocklist und/oder explizite
    Verbotsphrasen — der Judge muss das erkennen (passed=False, >=1 Verstoss)."""
    result = check_voice_consistency(text, voice_profile)
    assert result["passed"] is False, (
        f"[{profile_key}/{post_id}] sollte passed=False liefern (Verstoss erwartet), "
        f"aber der Post wurde durchgewunken (Score {result['score']})"
    )
    assert result["violations"], f"[{profile_key}/{post_id}] passed=False aber keine violations gemeldet"
