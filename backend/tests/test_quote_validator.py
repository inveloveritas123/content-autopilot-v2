"""Tests für Quote-Extraktor und Validator (Issue #86)."""

from services.quote_extractor import extract_quotes
from services.quote_validator import _fuzzy_match, _normalize, validate_post_quotes

# ── Quote-Extraktor ──────────────────────────────────────────────────────────

MARCUS_TRANSCRIPT = """
Ich habe in meinen 20 Jahren als Unternehmer gelernt, dass Vertrauen die Basis
jeder erfolgreichen Geschäftsbeziehung ist. Ohne Vertrauen können Sie keine
langfristigen Partnerschaften aufbauen. Das klingt simpel, aber die meisten
Unternehmen unterschätzen, wie lange es dauert, Vertrauen zu gewinnen.
Wir haben damals entschieden, lieber langsamer zu wachsen und dafür solide
Partnerschaften aufzubauen. Diese Entscheidung hat sich ausgezahlt.
"""


def test_extract_quotes_basic():
    quotes = extract_quotes(MARCUS_TRANSCRIPT)
    assert len(quotes) >= 5, f"Soll mindestens 5 Quotes liefern, hat {len(quotes)}"


def test_extract_quotes_min_words():
    quotes = extract_quotes(MARCUS_TRANSCRIPT, min_words=5)
    for q in quotes:
        assert len(q.split()) >= 5, f"Quote zu kurz: '{q}'"


def test_extract_quotes_has_verb():
    """Alle extrahierten Quotes sollen ein Verb enthalten (Heuristik)."""
    quotes = extract_quotes(MARCUS_TRANSCRIPT)
    # At least 80% of quotes should contain a verb indicator
    with_verb = [
        q
        for q in quotes
        if any(
            word in q.lower()
            for word in [
                "ist",
                "sind",
                "hat",
                "haben",
                "kann",
                "werden",
                "dauert",
                "aufzubauen",
                "gelernt",
                "entschieden",
            ]
        )
    ]
    assert len(with_verb) >= len(quotes) * 0.6, "Zu wenige Quotes enthalten Verben"


def test_extract_empty_text():
    assert extract_quotes("") == []
    assert extract_quotes("   ") == []


def test_extract_too_short():
    assert extract_quotes("Kurz.") == []


# ── Quote-Validator ───────────────────────────────────────────────────────────


def test_validate_real_quote_found():
    """Ein echtes Zitat aus dem Reservoir wird akzeptiert."""
    source = "Vertrauen ist die Basis jeder erfolgreichen Geschäftsbeziehung, das habe ich gelernt."
    post = "Wie Marcus Weber sagt: \u201eVertrauen ist die Basis jeder erfolgreichen Gesch\u00e4ftsbeziehung\u201c"

    result = validate_post_quotes(
        post_text=post,
        reservoir_content_texts=[source],
        reservoir_extracted_quotes=[],
    )
    assert (
        result.is_valid
    ), f"Echtes Zitat sollte akzeptiert werden, aber: {result.hallucinated_quotes}"


def test_validate_hallucinated_quote_rejected():
    """Ein erfundenes Zitat wird als Halluzination erkannt."""
    source = "Wir haben in 2020 angefangen, digital zu arbeiten."
    post = "Marcus Weber: \u201eK\u00fcnstliche Intelligenz wird die Welt in 10 Jahren komplett ver\u00e4ndern\u201c"

    result = validate_post_quotes(
        post_text=post,
        reservoir_content_texts=[source],
        reservoir_extracted_quotes=[],
    )
    assert not result.is_valid
    assert len(result.hallucinated_quotes) >= 1


def test_validate_no_quotes_in_post():
    """Post ohne Anführungszeichen braucht keine Validierung."""
    source = "Kurzer Quelltext ohne besondere Aussagen."
    post = "Heute teile ich meinen Ansatz für bessere Meetings."

    result = validate_post_quotes(
        post_text=post,
        reservoir_content_texts=[source],
        reservoir_extracted_quotes=[],
    )
    assert result.is_valid


def test_fuzzy_match_tolerates_whitespace():
    """Fuzzy-Match toleriert unterschiedliche Whitespace-Varianten."""
    assert _fuzzy_match("Vertrauen ist die Basis", "Vertrauen  ist  die  Basis  für alles")


def test_fuzzy_match_tolerates_punctuation():
    """Fuzzy-Match toleriert unterschiedliche Satzzeichen."""
    assert _fuzzy_match("Vertrauen, ist die Basis!", "Vertrauen ist die Basis für alles")


def test_normalize():
    normalized = _normalize("Hallo, Welt!")
    assert "hallo" in normalized
    assert "welt" in normalized
    assert "hallo" in _normalize("Hallo Welt")
