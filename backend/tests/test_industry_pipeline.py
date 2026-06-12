"""End-to-End-ähnliche Tests für Industry-Boost-Integration in Ideation.

Pure unit-tests — kein DB / API. Verifiziert dass die Code-Pfade
zusammenpassen.
"""

from __future__ import annotations


def test_apply_industry_boost_in_ideation_simulated():
    """Simuliert die Logik aus tasks/ideation_task.py:
    relevance_score wird nach industry-context boosted."""
    from services.industry_relevance import apply_industry_boost

    industry_context = {
        "trigger_woerter": [
            "kmu-coaching",
            "geschäftsmodelloptimierung",
            "strategieentwicklung",
            "leadership-training",
            "prozessoptimierung",
        ],
    }

    # Idea mit 2 Triggern → +1.0 Boost
    base = 6.0
    text = "Wie KMU-Coaching für Strategieentwicklung wirkt"
    new_score, info = apply_industry_boost(base, text, industry_context, cap=10.0)
    assert info["applied"] is True
    assert info["hits"] == 2
    assert new_score == 7.0


def test_no_industry_context_keeps_base_score():
    """Tenant ohne industry_context: relevance_score unverändert."""
    from services.industry_relevance import apply_industry_boost

    new_score, info = apply_industry_boost(7.5, "Beliebige Idee", None)
    assert new_score == 7.5
    assert info["applied"] is False


def test_industry_boost_caps_at_10():
    """Score wird nicht über cap=10.0 gehoben."""
    from services.industry_relevance import apply_industry_boost

    ctx = {"trigger_woerter": ["a", "b", "c", "d", "e", "f"]}
    new_score, info = apply_industry_boost(8.5, "a b c d e f g", ctx, cap=10.0)
    assert new_score == 10.0
    assert info["boost"] == 2.5  # hits >= 5 → MAX_BOOST


def test_p07_research_categories_subset_of_industry_themes():
    """P07-Kategorien-Spec passt zur Master-MD."""
    from tasks.p07_research_task import ALLOWED_CATEGORIES

    expected = {
        "rules_constraints",
        "demand_behavior",
        "tools_methods",
        "competition_market",
        "costs_resources",
        "emerging_topics",
    }
    assert expected == ALLOWED_CATEGORIES


def test_p12_variants_allowed_types():
    """4.2-Spec: nur 3 erlaubte Variant-Types."""
    from tasks.p12_variants_task import ALLOWED_VARIANT_TYPES

    assert {"hook", "story", "these"} == ALLOWED_VARIANT_TYPES


def test_memory_chunks_source_types_consistent_with_telegram_task():
    """memory_chunks-source_types stimmen mit Telegram-Task-Mappings überein."""
    from services.embedding_service import ALLOWED_SOURCE_TYPES

    assert "voice_telegram" in ALLOWED_SOURCE_TYPES
    assert "voice_whatsapp" in ALLOWED_SOURCE_TYPES
    assert "photo_telegram" in ALLOWED_SOURCE_TYPES
    assert "photo_whatsapp" in ALLOWED_SOURCE_TYPES
    assert "manual_note" in ALLOWED_SOURCE_TYPES
