"""
Unit-Tests fuer das Voice-Consistency-Gate (services/voice_gate.py).

Portiert aus persona-forge (style_gate.py/metrics.py/blocklist.py) fuer den
content-autopilot. Post-hoc-Check: MATTR/Satzlaenge/Fuellwoerter gegen ein
P03-Voice-Profile-Dict, Anti-KI-Blocklist, explizite Verbotsphrasen.

Dep-frei (nur services.voice_gate, stdlib). Kein LLM/DB/Netzwerk-Import.
"""

from __future__ import annotations

from services.voice_gate import (
    check_anti_ki_phrases,
    check_voice_consistency,
    compute_mattr,
    compute_metrics,
)

# ── MATTR-Berechnung (bekannte Eingaben) ─────────────────────────────────────


def test_mattr_all_unique_tokens_is_one():
    # 5 verschiedene Woerter, kuerzer als das Fenster (50) -> plaine TTR = 1.0
    assert compute_mattr("eins zwei drei vier fuenf") == 1.0


def test_mattr_full_repetition_is_low():
    # Ein einziges Wort zehnmal wiederholt -> TTR = 1/10 = 0.1 (starke Monotonie)
    val = compute_mattr("ja ja ja ja ja ja ja ja ja ja")
    assert val == 0.1


def test_mattr_empty_text_is_zero():
    assert compute_mattr("") == 0.0


def test_compute_metrics_bundle_has_expected_keys():
    m = compute_metrics("Das ist ein kurzer Test-Post. Er hat zwei Saetze.")
    assert set(m) >= {
        "tokens",
        "mattr",
        "avg_sentence_length",
        "sentence_length_stdev",
        "caps_ratio",
    }
    assert m["tokens"] == 9.0
    assert m["avg_sentence_length"] == 4.5


# ── Anti-KI-Phrasen-Treffer ───────────────────────────────────────────────────


def test_anti_ki_blocklist_hits_generic_opener():
    hits = check_anti_ki_phrases("In der heutigen schnelllebigen Welt müssen wir alle umdenken.")
    assert any("schnelllebigen Welt" in h for h in hits)


def test_anti_ki_blocklist_hits_hedging_and_als_ki():
    text = "Als KI kann ich sagen: Es ist wichtig zu beachten, dass alles gut wird."
    hits = check_anti_ki_phrases(text)
    assert any("Als KI" in h for h in hits)
    assert any("Es ist wichtig zu beachten" in h for h in hits)


def test_anti_ki_blocklist_no_hits_on_clean_text():
    hits = check_anti_ki_phrases("Heute war ein guter Tag im Garten.")
    assert hits == []


# ── forbidden_phrase-Treffer (vermeidungsprofil.nie_sagen) ───────────────────


def test_forbidden_phrase_from_profile_is_hard_violation():
    profile = {"vermeidungsprofil": {"nie_sagen": ["Mehrwert", "synergieren"]}}
    text = "Wir bieten euch echten Mehrwert für den Alltag."
    result = check_voice_consistency(text, profile)
    assert result["passed"] is False
    assert any("Mehrwert" in v for v in result["violations"])


def test_forbidden_phrase_accepts_dict_items_with_item_key():
    # nie_sagen darf laut P03-kanonisch auch dicts mit "item"/"grund" tragen.
    profile = {
        "vermeidungsprofil": {
            "nie_sagen": [{"item": "Zusammenfassend lässt sich sagen", "grund": "Aufsatz-Ton"}]
        }
    }
    text = "Zusammenfassend lässt sich sagen, dass wir gewonnen haben."
    result = check_voice_consistency(text, profile)
    assert result["passed"] is False


# ── Gesamtergebnis: guter Post passt, Verstoss faellt durch ──────────────────


def test_good_post_passes_with_forbidden_profile():
    profile = {"vermeidungsprofil": {"nie_sagen": ["Mehrwert", "synergieren"]}}
    text = "Heute war ein guter Tag im Garten. Die Tomaten reifen, endlich."
    result = check_voice_consistency(text, profile)
    assert result["passed"] is True
    assert result["violations"] == []
    assert result["score"] == 1.0


def test_bad_post_fails_and_lowers_score():
    profile = {"vermeidungsprofil": {"nie_sagen": ["Mehrwert"]}}
    text = "In der heutigen schnelllebigen Welt bieten wir echten Mehrwert für alle."
    result = check_voice_consistency(text, profile)
    assert result["passed"] is False
    assert len(result["violations"]) >= 2
    assert result["score"] < 1.0


# ── Robustheit bei leerem/minimalem voice_profile ────────────────────────────


def test_empty_voice_profile_does_not_crash_and_passes_clean_post():
    text = "Heute war ein guter Tag im Garten. Die Tomaten reifen, endlich."
    result = check_voice_consistency(text, {})
    assert result["passed"] is True
    assert result["metrics"]["tokens"] > 0


def test_minimal_voice_profile_missing_corridors_is_skipped_not_crashed():
    # satzarchitektur ohne numerische Baender, wortschatz ohne mattr-Feld:
    # beide Korridor-Checks muessen sauber uebersprungen werden.
    profile = {
        "satzarchitektur": {"laenge": "kurz, praegnant"},
        "wortschatz": {"signalwoerter": ["Garten"]},
    }
    text = "Heute war ein guter Tag im Garten. Die Tomaten reifen, endlich."
    result = check_voice_consistency(text, profile)
    assert result["passed"] is True


def test_empty_post_text_fails_without_crash():
    result = check_voice_consistency("", {})
    assert result["passed"] is False
    assert result["metrics"]["tokens"] == 0.0


def test_non_dict_voice_profile_does_not_crash():
    # Defensive: falls ein Aufrufer versehentlich None/etwas anderes uebergibt.
    text = "Heute war ein guter Tag im Garten."
    result = check_voice_consistency(text, None)  # type: ignore[arg-type]
    assert result["passed"] is True
