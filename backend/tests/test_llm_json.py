"""
Unit-Tests fuer services.llm_json.parse_json_from_text.

TDD: RED-GREEN-REFACTOR
Abgedeckte Pfade:
- reines JSON
- ```json-Fenced-Block
- ``` (ohne json) Fenced-Block
- eingebettetes JSON in Prosa (Brace-Matching)
- JSON in Prosa mit { } innerhalb von Strings (kein False-Positive)
- Markdown ohne JSON → ValueError
- leerer String → ValueError
"""

import pytest

from services.llm_json import _extract_first_json_object, parse_json_from_text

# ---------------------------------------------------------------------------
# _extract_first_json_object: Unit-Tests
# ---------------------------------------------------------------------------


class TestExtractFirstJsonObject:
    def test_simple_object(self):
        assert _extract_first_json_object('{"a": 1}') == '{"a": 1}'

    def test_object_embedded_in_text(self):
        text = 'Hier ist das Ergebnis: {"key": "value"} und noch mehr Text.'
        assert _extract_first_json_object(text) == '{"key": "value"}'

    def test_nested_object(self):
        text = 'Prefix {"outer": {"inner": 42}} Suffix'
        assert _extract_first_json_object(text) == '{"outer": {"inner": 42}}'

    def test_braces_inside_string_not_counted(self):
        text = 'Text {"key": "value with { braces } inside"} end'
        assert _extract_first_json_object(text) == '{"key": "value with { braces } inside"}'

    def test_escaped_quote_in_string(self):
        text = '{"key": "say \\"hello\\" ok"}'
        assert _extract_first_json_object(text) == '{"key": "say \\"hello\\" ok"}'

    def test_no_object_returns_none(self):
        assert _extract_first_json_object("keine JSON-Objekte hier") is None

    def test_unclosed_object_returns_none(self):
        assert _extract_first_json_object('{"unclosed": "yes"') is None


# ---------------------------------------------------------------------------
# parse_json_from_text: Hauptpfade
# ---------------------------------------------------------------------------


class TestParseJsonFromText:
    # Strategie 1: direktes JSON
    def test_pure_json(self):
        result = parse_json_from_text('{"name": "test", "value": 42}')
        assert result == {"name": "test", "value": 42}

    def test_pure_json_with_whitespace(self):
        result = parse_json_from_text('  \n{"a": 1}\n  ')
        assert result == {"a": 1}

    # Strategie 2: Fenced blocks
    def test_json_fenced_block(self):
        raw = '```json\n{"key": "val"}\n```'
        assert parse_json_from_text(raw) == {"key": "val"}

    def test_plain_fenced_block(self):
        raw = '```\n{"key": "val"}\n```'
        assert parse_json_from_text(raw) == {"key": "val"}

    def test_fenced_block_with_preamble(self):
        raw = 'Hier ist mein Output:\n```json\n{"x": 99}\n```\nFertig.'
        assert parse_json_from_text(raw) == {"x": 99}

    # Strategie 3: Brace-Matching
    def test_json_embedded_in_prose(self):
        raw = (
            "Vielen Dank fuer Ihre Anfrage. Hier ist das Voice-Profil:\n\n"
            '{"grundton": {"charakterisierung": "direkt"}, "satzarchitektur": {}}\n\n'
            "Ich hoffe, das hilft."
        )
        result = parse_json_from_text(raw)
        assert result["grundton"]["charakterisierung"] == "direkt"

    def test_json_in_prose_with_markdown_headers(self):
        raw = (
            "## Voice-Profil\n\n"
            "Basierend auf dem Transkript ergibt sich:\n\n"
            '{"tone": "informell", "level": 3}'
        )
        result = parse_json_from_text(raw)
        assert result == {"tone": "informell", "level": 3}

    def test_braces_in_string_values_dont_confuse_parser(self):
        raw = "Das Ergebnis ist:\n" '{"beispiel": "satz mit {placeholder} drin", "wert": 1}'
        result = parse_json_from_text(raw)
        assert result["beispiel"] == "satz mit {placeholder} drin"
        assert result["wert"] == 1

    # Fehlerfall: kein JSON vorhanden
    def test_markdown_without_json_raises(self):
        raw = (
            "## Analyse\n\n"
            "Das ist ein Markdown-Dokument ohne JSON.\n\n"
            "### Abschnitt\n\n"
            "Irgendein Text."
        )
        with pytest.raises(ValueError, match="Konnte kein JSON"):
            parse_json_from_text(raw)

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_json_from_text("")

    def test_fenced_block_with_invalid_json_falls_through_to_brace_matching(self):
        # Fence-Block ist kein gueltiges JSON, aber nach dem Block steht gueltiges JSON
        raw = "```json\n" "KEIN GUELTIGES JSON\n" "```\n\n" '{"fallback": true}'
        result = parse_json_from_text(raw)
        assert result == {"fallback": True}

    # #62: Modelle rutschen bei mehrabsätzigem Text (z.B. LinkedIn-Posts) gelegentlich
    # in echte Zeilenumbrueche statt \n-Escapes innerhalb von JSON-Strings — das
    # lehnt json.loads im strict-Mode hart ab, obwohl der Output vollstaendig und
    # eindeutig ist. Live in P12 beobachtet (#62 Schritt-0-E2E-Test).
    def test_literal_newline_inside_string_does_not_raise(self):
        raw = '```json\n{"post": "Erster Absatz.\n\nZweiter Absatz."}\n```'
        result = parse_json_from_text(raw)
        assert result["post"] == "Erster Absatz.\n\nZweiter Absatz."

    def test_literal_newline_inside_string_brace_matching_path(self):
        raw = 'Hier: {"post": "Zeile eins.\nZeile zwei."} Ende.'
        result = parse_json_from_text(raw)
        assert result["post"] == "Zeile eins.\nZeile zwei."
