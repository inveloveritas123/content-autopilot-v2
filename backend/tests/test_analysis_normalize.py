# AUDITED-2026-08-19 (louis-telegram-zwei-fehler): neu angelegt, vollstaendig geprueft.
"""Regressionstests fuer den Fehler, der Louis' Post-Generierung 1722-mal killte.

Der Beweis-Test ist `test_dict_liste_toetet_str_join` weiter unten: er zeigt
zuerst, dass der ALTE Ausdruck (`", ".join(...)`) mit exakt dem Wortlaut aus dem
Live-Log stirbt — und dann, dass der neue Weg dieselbe Eingabe uebersteht.

Live-Beleg (Worker-Log, Louis' Container, 7 Tage):
    Content generation failed for <uuid>:
    sequence item 0: expected str instance, dict found
1722 von 1722 Meldungen im identischen Wortlaut.

Dependency-frei: `services.analysis_normalize` importiert nur `logging`.
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys

import pytest

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _lade_modul():
    """Laedt services/analysis_normalize.py direkt — ohne services/__init__."""
    pfad = os.path.join(_BACKEND_DIR, "services", "analysis_normalize.py")
    spec = _ilu.spec_from_file_location("_analysis_normalize_test", pfad)
    modul = _ilu.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


_mod = _lade_modul()
normalize_text_list = _mod.normalize_text_list
join_analysis_list = _mod.join_analysis_list


# ---------------------------------------------------------------------------
# DER Beweis: ohne den Fix stirbt es, mit ihm nicht.
# ---------------------------------------------------------------------------


class TestDerEigentlicheFehler:
    #: Genau die Form, die im Live-Log zum Absturz fuehrte: das ERSTE Element
    #: ist bereits ein Dict ("item 0" in der Fehlermeldung).
    ANALYSE_WIE_IM_LOG = {
        "key_points": [
            {"point": "Waermepumpen lohnen sich auch im Altbau"},
            {"point": "Foerderung deckt bis zu 70 Prozent"},
        ],
        "content_angles": [
            {"angle": "Mythos Altbau entkraeften"},
        ],
        "summary": "Ein Beitrag ueber Waermepumpen.",
    }

    def test_dict_liste_toetet_str_join(self):
        """ROT-Beweis: der alte Ausdruck stirbt — mit dem Wortlaut aus dem Log."""
        with pytest.raises(TypeError) as exc:
            ", ".join(self.ANALYSE_WIE_IM_LOG["key_points"][:3])
        # Wortgleich mit der Meldung, die 1722-mal im Worker-Log stand.
        assert "expected str instance, dict found" in str(exc.value)
        assert "sequence item 0" in str(exc.value)

    def test_join_analysis_list_ueberlebt_dieselbe_eingabe(self):
        """GRUEN: derselbe Input, kein Absturz, brauchbarer Prompt-Text."""
        ergebnis = join_analysis_list(self.ANALYSE_WIE_IM_LOG, "key_points", limit=3)
        assert ergebnis == (
            "Waermepumpen lohnen sich auch im Altbau, Foerderung deckt bis zu 70 Prozent"
        )

    def test_der_inhalt_geht_nicht_verloren(self):
        """Der Text wird ausgepackt, nicht weggeworfen — sonst waere der Prompt leer."""
        ergebnis = join_analysis_list(self.ANALYSE_WIE_IM_LOG, "content_angles", limit=2)
        assert ergebnis == "Mythos Altbau entkraeften"


# ---------------------------------------------------------------------------
# normalize_text_list — die Formen, die real vorkommen
# ---------------------------------------------------------------------------


class TestNormalizeTextList:
    def test_saubere_stringliste_bleibt_unveraendert(self):
        assert normalize_text_list(["a", "b"]) == ["a", "b"]

    def test_leere_und_None_ergeben_leere_liste(self):
        assert normalize_text_list(None) == []
        assert normalize_text_list([]) == []

    def test_einzelner_string_wird_zur_liste(self):
        """Ein LLM liefert bei nur einem Punkt manchmal den blanken String."""
        assert normalize_text_list("nur ein Punkt") == ["nur ein Punkt"]

    def test_leerstrings_fliegen_raus(self):
        assert normalize_text_list(["a", "", "   ", "b"]) == ["a", "b"]

    def test_whitespace_wird_getrimmt(self):
        assert normalize_text_list(["  a  "]) == ["a"]

    @pytest.mark.parametrize(
        "schluessel",
        ["point", "text", "title", "value", "content", "name", "label", "angle"],
    )
    def test_bekannte_textschluessel_werden_ausgepackt(self, schluessel):
        assert normalize_text_list([{schluessel: "Inhalt"}]) == ["Inhalt"]

    def test_eindeutiger_einzelwert_wird_gerettet(self):
        """Unbekannter Schluessel, aber nur EIN String im Dict → eindeutig."""
        assert normalize_text_list([{"voellig_unbekannt": "Inhalt"}]) == ["Inhalt"]

    def test_mehrdeutiges_dict_wird_verworfen_statt_geraten(self):
        """Zwei Strings ohne bekannten Schluessel: raten waere schlimmer als weglassen."""
        assert normalize_text_list([{"aaa": "x", "bbb": "y"}]) == []

    def test_gemischte_liste_rettet_was_geht(self):
        assert normalize_text_list(["a", {"point": "b"}, None, {"x": {"y": 1}}]) == ["a", "b"]

    def test_zahlen_werden_zu_text(self):
        assert normalize_text_list([1, 2.5, True]) == ["1", "2.5", "True"]

    def test_dict_statt_liste_ergibt_leer(self):
        assert normalize_text_list({"key_points": ["a"]}) == []

    def test_verschachtelte_struktur_stuerzt_nicht_ab(self):
        assert normalize_text_list([[1, 2], {"a": {"b": "c"}}]) == []

    def test_wirft_niemals(self):
        """Zusicherung des Moduls: kein Eingabewert darf eine Exception ausloesen."""
        for wert in (None, 0, "", [], {}, set(), object(), [object()], [[]], 3.14):
            normalize_text_list(wert)  # darf nicht werfen


# ---------------------------------------------------------------------------
# join_analysis_list — 1:1-Ersatz fuer die alten Ausdruecke
# ---------------------------------------------------------------------------


class TestJoinAnalysisList:
    def test_verhaelt_sich_wie_join_bei_sauberen_daten(self):
        """Kein Verhaltensbruch dort, wo bisher alles funktionierte."""
        analyse = {"key_points": ["a", "b", "c"]}
        assert join_analysis_list(analyse, "key_points") == ", ".join(analyse["key_points"])

    def test_limit_ersetzt_die_alte_slice_notation(self):
        analyse = {"key_points": ["a", "b", "c", "d"]}
        assert join_analysis_list(analyse, "key_points", limit=3) == "a, b, c"

    def test_eigener_trenner(self):
        assert join_analysis_list({"k": ["a", "b"]}, "k", trenner=" | ") == "a | b"

    def test_fehlendes_feld_ergibt_leeren_string(self):
        assert join_analysis_list({}, "key_points") == ""

    def test_analyse_ist_kein_dict(self):
        assert join_analysis_list(None, "key_points") == ""
        assert join_analysis_list("kaputt", "key_points") == ""
