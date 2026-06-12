"""
Tests für sensitive_detector.py — Pattern-Schicht A only (kein LLM-Aufruf).
"""

from services.sensitive_detector import detect_sensitive_topics

# 10+ adversariale Posts (MÜSSEN geflaggt werden)
ADVERSARIAL = [
    ("AfD-Wähler sollten endlich aufhören zu jammern", ["politics"]),
    ("Bundeskanzler Scholz hat versagt und muss weg", ["politics"]),
    ("Als CDU-Mitglied sage ich: die Grünen zerstören Deutschland", ["politics"]),
    ("Allah ist der einzige wahre Gott und alle anderen Religionen sind falsch", ["religion"]),
    ("Die Bibel sagt dass Homosexualität Sünde ist", ["religion"]),
    ("Mein Produkt heilt Krebs nachweislich — Studien belegen das", ["health_claims"]),
    ("Kaufen Sie jetzt Bitcoin — sichere Rendite garantiert", ["financial_advice"]),
    ("Investiere jetzt in Ethereum, 100% Gewinn in 30 Tagen", ["financial_advice"]),
    ("Sie haben rechtlichen Anspruch darauf — klagen Sie ohne Anwalt", ["legal_advice"]),
    ("Volksverräter sitzen im Bundestag und verkaufen Deutschland", ["politics", "hate"]),
    ("Impfschaden ist real — das vertuscht die Regierung", ["health_claims", "politics"]),
    ("Steuern vermeiden legal mit diesem Trick", ["financial_advice"]),
]

# 10+ neutrale Posts (dürfen NICHT geflaggt werden)
NEUTRAL = [
    "Heute habe ich mit einem Kunden ein tolles Gespräch geführt.",
    "Mein Tipp für mehr Produktivität: früher aufstehen und den Tag planen.",
    "Als Unternehmensberater helfe ich meinen Kunden, ihre Prozesse zu optimieren.",
    "Fehler zu machen ist menschlich — daraus lernen ist professionell.",
    "Die Digitalisierung verändert, wie wir arbeiten. Bist du bereit?",
    "Unser Team hat diese Woche eine großartige Leistung erbracht.",
    "Drei Dinge, die ich in diesem Jahr über Führung gelernt habe.",
    "Warum Klarheit in der Kommunikation mehr wert ist als tausend Worte.",
    "Ich war skeptisch, aber dann hat es funktioniert — hier ist was passiert.",
    "Strategie ohne Umsetzung ist ein Wunschtraum.",
    "Was unterscheidet erfolgreiche Unternehmer von denen die scheitern?",
    "Rückblick auf meine ersten drei Jahre als Selbstständiger.",
]


def test_adversarial_posts_flagged():
    """Alle sensiblen Posts müssen geflaggt werden (Pattern-Layer only)."""
    for post, expected_categories in ADVERSARIAL:
        result = detect_sensitive_topics(post, use_llm=False)
        assert result.is_sensitive, f"MISS: '{post[:60]}...' should be flagged"
        for cat in expected_categories:
            assert cat in result.categories, f"Category '{cat}' missing for: '{post[:60]}'"


def test_neutral_posts_not_flagged():
    """Neutrale Posts dürfen nicht geflaggt werden (Pattern-Layer only)."""
    for post in NEUTRAL:
        result = detect_sensitive_topics(post, use_llm=False)
        assert not result.is_sensitive, f"FALSE POSITIVE: '{post[:60]}'"


def test_confidence_thresholds():
    """Hard-Escalation-Kategorien haben niedrigere Schwelle."""
    # health_claims hat threshold 0.3, nicht 0.6
    result = detect_sensitive_topics("Mein Produkt heilt Krebs", use_llm=False)
    assert result.is_sensitive
    assert result.severity == "high"


def test_empty_post_not_flagged():
    result = detect_sensitive_topics("", use_llm=False)
    assert not result.is_sensitive


def test_flagged_phrases_populated():
    result = detect_sensitive_topics("Die AfD hat die Bundestagswahl gewonnen", use_llm=False)
    assert result.is_sensitive
    assert len(result.flagged_phrases) >= 1


def test_standalone_hate_flagged():
    """Hate-Kategorie allein muss zuverlässig triggern."""
    hate_posts = [
        "Volksverräter sitzen im Bundestag",
        "Diese Überfremdung muss gestoppt werden",
        "Rassismus ist ein echtes Problem in unserer Gesellschaft",  # should flag
    ]
    for post in hate_posts:
        result = detect_sensitive_topics(post, use_llm=False)
        assert result.is_sensitive, f"Hate post not flagged: '{post}'"
        assert "hate" in result.categories or "politics" in result.categories
