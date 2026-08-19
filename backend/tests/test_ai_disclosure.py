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


# ---------------------------------------------------------------------------
# Art. 50 Abs. 1 — Kennzeichnung der INTERAKTION (nicht des Inhalts)
# ---------------------------------------------------------------------------
#
# Die Tests oben decken Abs. 4 ab (KI-erzeugter Inhalt). Abs. 1 ist ein
# eigener Tatbestand: Wer mit einem KI-System interagiert, muss das erfahren.
# Beide Pflichten sind unabhängig — deshalb prüft der letzte Test hier
# ausdrücklich, dass sie sich nicht gegenseitig ersetzen.

from services.ai_disclosure import (
    CHAT_AI_HINWEIS,
    chat_ai_hinweis_block,
    hat_chat_ai_hinweis,
)


def test_chat_hinweis_nennt_die_ki():
    """Der Hinweis muss die KI-Interaktion benennen — das ist der Kern von Abs. 1."""
    assert "KI-Assistenten" in CHAT_AI_HINWEIS


def test_chat_hinweis_nennt_die_grenze():
    """Nicht nur 'ist KI', sondern auch: die Freigabe bleibt beim Menschen.

    Das ist keine Zierde — es beschreibt das HITL-Modell korrekt und beugt der
    Fehlannahme vor, der Bot poste selbstständig.
    """
    assert "Freigabe" in CHAT_AI_HINWEIS


def test_block_ist_abgesetzt():
    """Der Hinweis ist als eigener Block erkennbar, nicht Teil des Fließtexts."""
    block = chat_ai_hinweis_block()
    assert block.startswith("\n\n")
    assert "─────" in block


def test_erkennung_findet_den_hinweis():
    assert hat_chat_ai_hinweis(chat_ai_hinweis_block()) is True


def test_erkennung_ohne_falschpositiv():
    assert hat_chat_ai_hinweis("Ein ganz normaler Text ohne Hinweis.") is False
    assert hat_chat_ai_hinweis("") is False


def test_abs1_und_abs4_sind_unabhaengig():
    """⛔ Der Post-Hinweis (Abs. 4) ersetzt den Chat-Hinweis (Abs. 1) NICHT.

    Beide Tatbestände bestehen nebeneinander. Wer das verwechselt, hält die
    Pflicht für erfüllt, weil ja 'irgendwo KI dransteht' — genau der Zustand
    vor dem 17.08.2026, als nur Post-Entwürfe gekennzeichnet waren.
    """
    post_mit_abs4 = append_ai_notice("Ein Entwurf.")
    assert hat_chat_ai_hinweis(post_mit_abs4) is False

    chat_block = chat_ai_hinweis_block()
    assert "KI-gestützt in deiner Stimme erstellt" not in chat_block
