"""Tests für services.industry_relevance (Phase 4.4)."""
from __future__ import annotations


def test_count_trigger_hits_empty():
    from services.industry_relevance import count_trigger_hits
    assert count_trigger_hits("", []) == 0
    assert count_trigger_hits("foo", []) == 0
    assert count_trigger_hits("", ["bar"]) == 0


def test_count_trigger_hits_basic():
    from services.industry_relevance import count_trigger_hits
    text = "Vertrauen ist Basis im Coaching für Steuerberater"
    triggers = ["coaching", "steuerberater", "investment"]
    assert count_trigger_hits(text, triggers) == 2


def test_count_trigger_hits_case_insensitive():
    from services.industry_relevance import count_trigger_hits
    assert count_trigger_hits("Coaching ist KING", ["coaching"]) == 1
    assert count_trigger_hits("MANAGEMENT-Skills", ["management"]) == 1


def test_count_trigger_hits_dedupe():
    """Doppelte Trigger-Wörter zählen nur 1×."""
    from services.industry_relevance import count_trigger_hits
    assert count_trigger_hits("coaching coaching coaching", ["coaching"]) == 1
    assert count_trigger_hits("X", ["coaching", "coaching"]) == 0


def test_compute_industry_boost_no_hits():
    from services.industry_relevance import compute_industry_boost
    assert compute_industry_boost("Hallo", ["foo", "bar"]) == 0.0


def test_compute_industry_boost_table():
    from services.industry_relevance import compute_industry_boost, HIT_BOOST, MAX_BOOST
    assert compute_industry_boost("a", ["a"]) == HIT_BOOST[1]
    assert compute_industry_boost("a b", ["a", "b"]) == HIT_BOOST[2]
    assert compute_industry_boost("a b c", ["a", "b", "c"]) == HIT_BOOST[3]
    assert compute_industry_boost("a b c d", ["a", "b", "c", "d"]) == HIT_BOOST[4]
    assert compute_industry_boost("a b c d e", ["a", "b", "c", "d", "e"]) == HIT_BOOST[5]
    # Überlauf
    assert compute_industry_boost("a b c d e f", ["a", "b", "c", "d", "e", "f"]) == MAX_BOOST


def test_apply_industry_boost_no_context():
    from services.industry_relevance import apply_industry_boost
    score, info = apply_industry_boost(7.0, "irgend was", None)
    assert score == 7.0
    assert info["applied"] is False


def test_apply_industry_boost_no_triggers():
    from services.industry_relevance import apply_industry_boost
    score, info = apply_industry_boost(7.0, "x", {"trigger_woerter": []})
    assert score == 7.0
    assert info["applied"] is False


def test_apply_industry_boost_real():
    from services.industry_relevance import apply_industry_boost
    ctx = {"trigger_woerter": ["coaching", "selbstständig", "klarheit"]}
    score, info = apply_industry_boost(
        6.0, "Klarheit im Coaching für Selbstständige", ctx
    )
    assert info["applied"] is True
    assert info["hits"] == 3
    assert score == 6.0 + 1.5  # 3-hit boost
    assert info["boost"] == 1.5


def test_apply_industry_boost_cap_at_10():
    from services.industry_relevance import apply_industry_boost
    ctx = {"trigger_woerter": ["a", "b", "c", "d", "e", "f"]}
    score, info = apply_industry_boost(9.0, "a b c d e f", ctx, cap=10.0)
    assert score == 10.0  # capped
    assert info["boost"] == 2.5
