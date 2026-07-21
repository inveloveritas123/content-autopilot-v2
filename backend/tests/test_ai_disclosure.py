"""Tests für die KI-Kennzeichnung (W6, EU-AI-Act Art. 50)."""

from services.ai_disclosure import append_ai_notice


def test_notice_appended():
    out = append_ai_notice("Mein toller Post über Handwerk.")
    assert "Mein toller Post über Handwerk." in out
    assert "KI-gestützt in deiner Stimme erstellt" in out
    # Der Hinweis ist abtrennbar (Trennlinie).
    assert "— — —" in out


def test_notice_idempotent():
    once = append_ai_notice("Post.")
    twice = append_ai_notice(once)
    assert once == twice
    assert once.count("KI-gestützt in deiner Stimme erstellt") == 1


def test_empty_input_unchanged():
    assert append_ai_notice("") == ""


def test_post_text_precedes_notice():
    out = append_ai_notice("ORIGINAL")
    assert out.index("ORIGINAL") < out.index("KI-gestützt")
