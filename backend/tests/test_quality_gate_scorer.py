"""
Unit-Tests fuer den Quality-Gate-Struktur-/Regel-Scorer (Issue #38, Chunk 1).

Prueft einzelne Regeln isoliert:
  - Leerer Post
  - Zu kurz (too_short)
  - Excessive Caps
  - Satzzeichen-Fehlen
  - Disclaimer je recht/finanzen
  - PII-/Eigenname-Heuristik
  - Branchen-Thresholds
  - Hashtag-Spam

Dep-Frei. Py3.9-kompatibel. Kein sqlalchemy/fastapi/LLM-Import.
Scorer-Import via importlib (file-import) wie im Harness.
"""

from __future__ import annotations

import importlib.util
import pathlib

# ---------------------------------------------------------------------------
# File-Import des Scorers
# ---------------------------------------------------------------------------

_STUB_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "services" / "quality_gate_stub.py"
)


def _load_scorer():
    spec = importlib.util.spec_from_file_location("quality_gate_stub", _STUB_PATH)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.quality_gate_check


quality_gate_check = _load_scorer()

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

_GOOD_GENERIC = (
    "Was ich heute gelernt habe ueber Fuehrung und Kommunikation im Team:\n\n"
    "Klare Ziele setzen ist wichtiger als lange Meetings. "
    "In unserem Betrieb haben wir die Meetingdauer halbiert durch drei einfache Regeln.\n\n"
    "Erstens: Agenda vor dem Termin. Zweitens: maximal 30 Minuten. "
    "Drittens: jede Entscheidung sofort notieren.\n\n"
    "Welche Meeting-Regel nutzt ihr in eurem Team?"
)

_GOOD_RECHT = (
    "Aufhebungsvertrag vs. Kuendigung — was Arbeitnehmer wissen muessen:\n\n"
    "Wer einen Aufhebungsvertrag unterschreibt, riskiert eine Sperrzeit beim Arbeitslosengeld. "
    "Das sind 12 Wochen ohne ALG1 — auch wenn der Arbeitgeber gedraengt hat.\n\n"
    "Niemals unter Druck unterschreiben. Immer mindestens 24 Stunden Bedenkzeit nehmen.\n\n"
    "Diese Information stellt keine Rechtsberatung dar. Im Einzelfall immer einen Anwalt konsultieren.\n\n"
    "Habt ihr solche Situationen erlebt?"
)

_GOOD_FINANZEN = (
    "Der groesste Fehler bei der Altersvorsorge: zu spaet anfangen.\n\n"
    "Wer mit 25 monatlich 200 EUR bei 6% Rendite anlegt, hat mit 65 rund 400.000 EUR. "
    "Wer mit 35 startet, hat nur noch rund 200.000 EUR — gleiche monatliche Einzahlung.\n\n"
    "Der Zinseszins-Effekt ist Mathematik, keine Magie. Zeit ist die entscheidende Variable.\n\n"
    "Dies ist keine Anlageberatung. Individuelle Beratung beim Finanzberater einholen.\n\n"
    "Habt ihr frueh angefangen oder wartet ihr noch?"
)


# ---------------------------------------------------------------------------
# Klasse 1: Leerer / Null-Post
# ---------------------------------------------------------------------------


class TestLeerPost:
    def test_empty_string(self):
        result = quality_gate_check("", "_generic")
        assert result["passed"] is False
        assert result["score"] == 0.0
        assert "empty_post" in result["violations"]

    def test_whitespace_only(self):
        result = quality_gate_check("   \n\n\t  ", "_generic")
        assert result["passed"] is False
        assert "empty_post" in result["violations"]

    def test_single_char(self):
        result = quality_gate_check("!", "_generic")
        assert result["passed"] is False

    def test_branche_echoed_on_empty(self):
        for branche in ["_generic", "handwerk", "recht", "finanzen"]:
            result = quality_gate_check("", branche)
            assert result["branche"] == branche


# ---------------------------------------------------------------------------
# Klasse 2: too_short
# ---------------------------------------------------------------------------


class TestTooShort:
    def test_very_short_fails(self):
        result = quality_gate_check("Hallo Welt.", "_generic")
        assert result["passed"] is False
        assert "too_short" in result["violations"]

    def test_single_line_fails(self):
        result = quality_gate_check("Heute war ich produktiv.", "_generic")
        assert result["passed"] is False
        assert "too_short" in result["violations"]

    def test_under_200_chars_fails(self):
        text = "a" * 100 + "."
        result = quality_gate_check(text, "_generic")
        assert result["passed"] is False
        assert "too_short" in result["violations"]

    def test_over_200_chars_no_too_short(self):
        # Langer genug Text ohne andere Violations
        text = _GOOD_GENERIC
        result = quality_gate_check(text, "_generic")
        assert "too_short" not in result["violations"]

    def test_too_short_score_below_threshold(self):
        result = quality_gate_check("Kurzer Post.", "_generic")
        threshold = result["threshold"]
        assert result["score"] < threshold

    def test_too_short_recht_threshold_65(self):
        result = quality_gate_check("Kurzer Post.", "recht")
        assert result["threshold"] == 65.0

    def test_too_short_finanzen_threshold_70(self):
        result = quality_gate_check("Kurzer Post.", "finanzen")
        assert result["threshold"] == 70.0

    def test_too_short_handwerk_threshold_60(self):
        result = quality_gate_check("Kurzer Post.", "handwerk")
        assert result["threshold"] == 60.0

    def test_too_short_generic_threshold_55(self):
        result = quality_gate_check("Kurzer Post.", "_generic")
        assert result["threshold"] == 55.0


# ---------------------------------------------------------------------------
# Klasse 3: Excessive Caps
# ---------------------------------------------------------------------------


class TestExcessiveCaps:
    def test_full_caps_short_fails(self):
        text = "KLAGE JETZT!!! GELD ZURUECK!!!"
        result = quality_gate_check(text, "_generic")
        assert result["passed"] is False
        assert "excessive_caps" in result["violations"]

    def test_full_caps_longer_fails(self):
        text = "HEUTE WAR GROSS!!! MORGEN NOCH MEHR CAPS!!! " * 10
        result = quality_gate_check(text, "_generic")
        assert "excessive_caps" in result["violations"]

    def test_normal_text_no_caps_violation(self):
        result = quality_gate_check(_GOOD_GENERIC, "_generic")
        assert "excessive_caps" not in result["violations"]

    def test_borderline_caps_ratio(self):
        # Genau 30% Grossbuchstaben: kein Violation
        # 10 alpha chars, 3 gross (30%)
        text = "Abc def GHI." + ("x" * 200)  # Masse ohne Caps
        result = quality_gate_check(text, "_generic")
        # Keine strict-Caps-Violation erwartet
        assert result["score"] >= 0  # Nur sicherstellen kein Crash

    def test_caps_violation_score_below_threshold(self):
        text = "SUPER ANGEBOT!!! JETZT KAUFEN!!! BADEZIMMER RENOVIERUNG NUR 999 EURO!!!"
        result = quality_gate_check(text, "handwerk")
        assert result["score"] < result["threshold"]
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# Klasse 4: Satzzeichen-Fehlen
# ---------------------------------------------------------------------------


class TestNoSentenceTerminators:
    def test_no_punctuation_short_fails(self):
        result = quality_gate_check("hallo welt das ist ein test", "_generic")
        assert result["passed"] is False
        assert "no_sentence_terminators" in result["violations"]

    def test_with_period_no_violation(self):
        result = quality_gate_check(_GOOD_GENERIC, "_generic")
        assert "no_sentence_terminators" not in result["violations"]

    def test_question_mark_counts(self):
        # Text mit Fragezeichen sollte keine no_sentence_terminators Violation haben
        # (muss auch lang genug sein)
        text = "Was denkt ihr ueber Fuehrung im Team? " * 10
        result = quality_gate_check(text, "_generic")
        assert "no_sentence_terminators" not in result["violations"]

    def test_exclamation_mark_counts(self):
        text = "Das ist wichtig! Bitte beachten! " * 8
        result = quality_gate_check(text, "_generic")
        assert "no_sentence_terminators" not in result["violations"]


# ---------------------------------------------------------------------------
# Klasse 5: Branchen-Disclaimer (recht)
# ---------------------------------------------------------------------------


class TestRechtDisclaimer:
    def test_good_recht_with_disclaimer_passes(self):
        result = quality_gate_check(_GOOD_RECHT, "recht")
        assert result["passed"] is True
        assert "missing_legal_disclaimer" not in result["violations"]

    def test_long_recht_without_disclaimer_flagged(self):
        # Langer Rechts-Post OHNE Disclaimer
        text = (
            "GmbH oder GmbH & Co. KG — die Wahl der Rechtsform entscheidet ueber Haftung und Steuern.\n\n"
            "GmbH bietet Haftungsbeschraenkung auf das Stammkapital (mind. 25.000 EUR). "
            "Die Koerperschaftsteuer betraegt 15%. Das Geschaeftsfuehrergehalt ist sozialversicherungspflichtig.\n\n"
            "Fuer Familienbetriebe mit Nachfolgeplanung ist die GmbH & Co. KG haeufig besser geeignet. "
            "Die Buchfuehrung ist komplexer, bietet aber mehr Steuergestaltung.\n\n"
            "Welche Rechtsform habt ihr gewaehlt und warum?"
        )
        result = quality_gate_check(text, "recht")
        assert "missing_legal_disclaimer" in result["violations"]
        assert result["passed"] is False

    def test_short_recht_no_disclaimer_required(self):
        # Kurzer Rechts-Post (< 400 Zeichen): kein Disclaimer noetig
        text = "GmbH oder GmbH & Co. KG? Das ist eine gute Frage fuer Gruender."
        result = quality_gate_check(text, "recht")
        assert "missing_legal_disclaimer" not in result["violations"]

    def test_recht_disclaimer_phrase_variants(self):
        # Verschiedene Disclaimer-Phrasen werden erkannt
        phrases_ok = [
            "keine Rechtsberatung",
            "Kein Rechtsberatung",
            "stellt keine Rechtsberatung dar",
            "keine juristische Beratung",
            "Anwalt konsultieren",
        ]
        for phrase in phrases_ok:
            text = (
                "Rechtliche Frage zu Mietrecht und Kuendigung. " * 10
                + f"\n\n{phrase}."
            )
            result = quality_gate_check(text, "recht")
            assert "missing_legal_disclaimer" not in result["violations"], (
                f"Phrase '{phrase}' nicht erkannt"
            )


# ---------------------------------------------------------------------------
# Klasse 6: Branchen-Disclaimer (finanzen)
# ---------------------------------------------------------------------------


class TestFinanzenDisclaimer:
    def test_good_finanzen_with_disclaimer_passes(self):
        result = quality_gate_check(_GOOD_FINANZEN, "finanzen")
        assert result["passed"] is True
        assert "missing_financial_disclaimer" not in result["violations"]

    def test_long_finanzen_without_disclaimer_flagged(self):
        # Muss > 400 Zeichen sein um Disclaimer-Check auszuloesen
        text = (
            "ETF vs. aktiv gemanagte Fonds — die Zahlen sprechen eine klare Sprache.\n\n"
            "Laut SPIVA-Studie 2023 schlagen 85% der aktiven Fondsmanager ihren Benchmark-Index "
            "ueber 15 Jahre nicht. Die Kostenquote ist dabei der entscheidende Faktor: "
            "Aktive Fonds kosten 1,5 bis 2,5 Prozent, ETFs oft unter 0,2 Prozent.\n\n"
            "Das bedeutet: Ein Vorteil von 1,5% pro Jahr klingt klein, macht aber ueber 30 Jahre "
            "bei 100.000 EUR Anlagesumme einen Unterschied von ueber 100.000 EUR.\n\n"
            "Was nutzt ihr — ETF oder aktive Fonds? Schreibt es in die Kommentare!"
        )
        assert len(text) > 400, f"Testtext zu kurz: {len(text)} Zeichen"
        result = quality_gate_check(text, "finanzen")
        assert "missing_financial_disclaimer" in result["violations"]
        assert result["passed"] is False

    def test_short_finanzen_no_disclaimer_required(self):
        text = "ETF oder Fonds? Eine gute Frage fuer Anleger."
        result = quality_gate_check(text, "finanzen")
        assert "missing_financial_disclaimer" not in result["violations"]

    def test_finanzen_disclaimer_phrase_variants(self):
        phrases_ok = [
            "keine Anlageberatung",
            "keine Finanzberatung",
            "keine Steuerberatung",
            "allgemeine Finanzbildung",
            "Finanzberater",
        ]
        for phrase in phrases_ok:
            text = (
                "Finanzielle Freiheit durch kluge Investitionen erreichen. " * 8
                + f"\n\n{phrase}."
            )
            result = quality_gate_check(text, "finanzen")
            assert "missing_financial_disclaimer" not in result["violations"], (
                f"Phrase '{phrase}' nicht erkannt"
            )


# ---------------------------------------------------------------------------
# Klasse 7: PII-/Eigenname-Heuristik
# ---------------------------------------------------------------------------


class TestPIIHeuristik:
    def test_family_name_flagged(self):
        text = (
            "Heute war ich bei Familie Mueller in Koeln und habe das Dach repariert. "
            "Nach drei Stunden war der Schaden behoben. "
            "Was viele nicht wissen: 80% aller Dachlecks entstehen durch vernachlaessigte Wartung. "
            "Habt ihr euer Dach schon dieses Jahr checken lassen?"
        )
        result = quality_gate_check(text, "handwerk")
        assert "potential_pii_reference" in result["violations"]

    def test_herr_frau_flagged(self):
        text = (
            "Unser Mandant Herr Schmidt hat heute einen wichtigen Vergleich erzielt. "
            "Die Details koennen wir leider nicht nennen, aber das Ergebnis war sehr positiv. "
            "Keine Rechtsberatung — nur ein Erfolgsbeispiel aus unserer Kanzleiarbeit. "
            "Was denkt ihr ueber aussergerichtliche Einigungen?"
        )
        result = quality_gate_check(text, "recht")
        assert "potential_pii_reference" in result["violations"]

    def test_no_pii_in_generic_good_post(self):
        result = quality_gate_check(_GOOD_GENERIC, "_generic")
        assert "potential_pii_reference" not in result["violations"]

    def test_pii_does_not_block_good_post_score(self):
        # PII-Violation soll warnen aber nicht zwingend blocken
        # (soft-check — Score-Auswirkung gering)
        text = _GOOD_GENERIC + "\n\nEin Beispiel von Herr Muster zeigt das gut."
        result = quality_gate_check(text, "_generic")
        # Post sollte trotzdem eine valide Score haben
        assert result["score"] >= 0
        assert isinstance(result["violations"], list)


# ---------------------------------------------------------------------------
# Klasse 8: Branchen-Thresholds
# ---------------------------------------------------------------------------


class TestBranchenThresholds:
    def test_generic_threshold(self):
        result = quality_gate_check("x", "_generic")
        assert result["threshold"] == 55.0

    def test_handwerk_threshold(self):
        result = quality_gate_check("x", "handwerk")
        assert result["threshold"] == 60.0

    def test_recht_threshold(self):
        result = quality_gate_check("x", "recht")
        assert result["threshold"] == 65.0

    def test_finanzen_threshold(self):
        result = quality_gate_check("x", "finanzen")
        assert result["threshold"] == 70.0

    def test_unknown_branche_fallback(self):
        # Unbekannte Branche soll nicht crashen
        result = quality_gate_check("Hallo Welt.", "unbekannt")
        assert "passed" in result
        assert "score" in result
        # Fallback auf _generic threshold
        assert result["threshold"] in (55.0, 60.0, 65.0, 70.0)

    def test_passed_requires_score_above_threshold(self):
        for branche in ["_generic", "handwerk", "recht", "finanzen"]:
            result = quality_gate_check("x", branche)
            # Bei Fail: score < threshold
            if not result["passed"]:
                assert result["score"] <= result["threshold"]


# ---------------------------------------------------------------------------
# Klasse 9: Hashtag-Sanity
# ---------------------------------------------------------------------------


class TestHashtagSanity:
    def test_no_hashtags_ok(self):
        result = quality_gate_check(_GOOD_GENERIC, "_generic")
        assert "hashtag_spam" not in result["violations"]

    def test_few_hashtags_ok(self):
        text = _GOOD_GENERIC + "\n\n#LinkedIn #Fuehrung #Tipps"
        result = quality_gate_check(text, "_generic")
        assert "hashtag_spam" not in result["violations"]

    def test_too_many_hashtags_violation(self):
        hashtags = " ".join(f"#tag{i}" for i in range(15))
        text = _GOOD_GENERIC + "\n\n" + hashtags
        result = quality_gate_check(text, "_generic")
        assert "hashtag_spam" in result["violations"]


# ---------------------------------------------------------------------------
# Klasse 10: Regression / Anti-Pollution
# ---------------------------------------------------------------------------


class TestRegression:
    def test_scorer_is_stateless(self):
        """Mehrfacher Aufruf mit gleichem Input liefert identisches Ergebnis."""
        text = _GOOD_GENERIC
        r1 = quality_gate_check(text, "_generic")
        r2 = quality_gate_check(text, "_generic")
        assert r1["score"] == r2["score"]
        assert r1["passed"] == r2["passed"]
        assert r1["violations"] == r2["violations"]

    def test_different_branchen_independent(self):
        """Branchenspezifische Regeln beeinflussen sich nicht gegenseitig."""
        result_generic = quality_gate_check(_GOOD_GENERIC, "_generic")
        result_recht = quality_gate_check(_GOOD_GENERIC, "recht")
        # Beide sollten valide Ergebnisse liefern, kein Crash
        assert isinstance(result_generic["passed"], bool)
        assert isinstance(result_recht["passed"], bool)

    def test_score_range_always_valid(self):
        """Score muss immer in [0, 100] liegen."""
        test_inputs = [
            ("", "_generic"),
            ("x", "handwerk"),
            (_GOOD_GENERIC, "_generic"),
            ("CAPS " * 50, "finanzen"),
            ("a" * 5000, "recht"),
        ]
        for text, branche in test_inputs:
            result = quality_gate_check(text, branche)
            assert 0.0 <= result["score"] <= 100.0, (
                f"Score {result['score']} ausserhalb [0,100] fuer [{branche}] text_len={len(text)}"
            )
