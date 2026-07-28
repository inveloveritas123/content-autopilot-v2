"""
test_issue29_canonical_reader.py — Mapping-Tests für Issue #29 Backend-Reader Rewire.

Testet die kanonischen Feld-Pfade in:
  1. api/brand_voice.py  — EDITABLE_ROOT_KEYS (Allow-List)
  2. api/dialogue.py     — _tone-Extraktion (grundton.charakterisierung)
  3. api/pipeline.py     — _tone_val + _avoid_val (vermeidungsprofil.nie_sagen)

EDITABLE_ROOT_KEYS wird per Quelltext-Parsing geladen (brand_voice.py importiert
datetime.UTC = Py3.11+, sqlalchemy, fastapi → nicht via importlib auf Py3.9 ladbar).
Mapping-Helfer für tone/avoid sind dep-frei direkt im Test definiert (exakte
Kopien der API-Logik nach Issue-#29-Rewire).
"""

import ast
import re
from pathlib import Path

_BACKEND_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Helfer: EDITABLE_ROOT_KEYS aus Quelltext extrahieren (Py3.9-kompatibel)
# ---------------------------------------------------------------------------


def _load_editable_root_keys() -> dict:
    """Parst EDITABLE_ROOT_KEYS aus api/brand_voice.py via ast.literal_eval.

    Umgeht den Py3.11+-Import (datetime.UTC) und alle schweren Deps (sqlalchemy,
    fastapi). Nur die Konstante wird extrahiert, kein Modul-Code ausgeführt.
    """
    src = (_BACKEND_ROOT / "api" / "brand_voice.py").read_text(encoding="utf-8")
    # Suche den Block  EDITABLE_ROOT_KEYS: dict[str, list[str]] = { ... }
    # Bis zum Ende des Dict-Literals (schließende '}' auf eigener Zeile nach Einrückung)
    m = re.search(
        r"^EDITABLE_ROOT_KEYS\s*:.*?=\s*(\{.*?\n\})",
        src,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        raise RuntimeError("EDITABLE_ROOT_KEYS nicht in brand_voice.py gefunden")
    raw = m.group(1)
    # ast.literal_eval versteht dict/list/str literals — kein exec nötig
    return ast.literal_eval(raw)


# ---------------------------------------------------------------------------
# Pure helpers: extrahiert aus dialogue.py / pipeline.py für dep-freie Tests
# ---------------------------------------------------------------------------


def _extract_tone(voice_profile: dict, default: str = "") -> str:
    """
    Exakte Kopie der tone-Extraktion aus api/dialogue.py (nach Issue-#29-Rewire).
    Kanonisch: grundton.charakterisierung; Alt-Row-Fallback: tonalitaet.grundton.
    """
    return (
        voice_profile.get("tone")
        or (
            voice_profile.get("grundton", {}).get("charakterisierung", "")
            if isinstance(voice_profile.get("grundton"), dict)
            else ""
        )
        or (
            voice_profile.get("tonalitaet", {}).get("grundton", "")
            if isinstance(voice_profile.get("tonalitaet"), dict)
            else ""
        )
        or default
    )


def _extract_avoid(voice_profile: dict):
    """
    Exakte Kopie der avoid-Extraktion aus api/pipeline.py (nach Issue-#29-Rewire).
    Kanonisch: vermeidungsprofil.nie_sagen; Alt-Row-Fallback: vermeidungsregeln.
    Gibt bereinigte Liste/String zurück (wie pipeline.py).
    """
    _canonical_nie_sagen = (
        voice_profile.get("vermeidungsprofil", {}).get("nie_sagen")
        if isinstance(voice_profile.get("vermeidungsprofil"), dict)
        else None
    )
    if isinstance(_canonical_nie_sagen, list) and _canonical_nie_sagen:
        return [
            (e.get("item") or str(e)) if isinstance(e, dict) else str(e)
            for e in _canonical_nie_sagen
        ]
    # Alt-Row-Fallback  (str | list not valid in isinstance on Py3.9 → tuple)
    return voice_profile.get("topics_avoid") or (
        voice_profile.get("vermeidungsregeln")
        if isinstance(voice_profile.get("vermeidungsregeln"), str | list)
        else None
    )


# ============================================================================
# 1. EDITABLE_ROOT_KEYS — brand_voice.py
# ============================================================================

_EDITABLE_ROOT_KEYS = _load_editable_root_keys()


class TestEditableRootKeys:
    """EDITABLE_ROOT_KEYS spiegeln die kanonischen P03/P04-Top-Level-Keys."""

    def test_voice_profile_has_canonical_grundton(self):
        """voice_profile: 'grundton' muss in der Allow-List sein (kanonisch, p03.schema.json:61)."""
        assert "grundton" in _EDITABLE_ROOT_KEYS["voice_profile"]

    def test_voice_profile_has_canonical_vermeidungsprofil(self):
        """voice_profile: 'vermeidungsprofil' (nicht 'vermeidungsregeln') muss enthalten sein."""
        assert "vermeidungsprofil" in _EDITABLE_ROOT_KEYS["voice_profile"]

    def test_voice_profile_union_keeps_v2_tonalitaet(self):
        """voice_profile: v2-Key 'tonalitaet' bleibt in der Union (Alt-Rows editierbar, Übergang)."""
        assert "tonalitaet" in _EDITABLE_ROOT_KEYS["voice_profile"]

    def test_voice_profile_union_keeps_v2_vermeidungsregeln(self):
        """voice_profile: v2-Key 'vermeidungsregeln' bleibt in der Union (Übergang)."""
        assert "vermeidungsregeln" in _EDITABLE_ROOT_KEYS["voice_profile"]

    def test_voice_profile_union_keeps_v2_kernthemen(self):
        """voice_profile: v2-Key 'kernthemen' (kein kanon. Ziel) bleibt für Alt-Rows editierbar."""
        assert "kernthemen" in _EDITABLE_ROOT_KEYS["voice_profile"]

    def test_voice_profile_union_keeps_v2_stilprinzipien(self):
        """voice_profile: v2-Key 'stilprinzipien' bleibt in der Union (kanon. Ziel: satzarchitektur)."""
        assert "stilprinzipien" in _EDITABLE_ROOT_KEYS["voice_profile"]

    def test_voice_profile_union_keeps_v2_schreibrhythmus(self):
        """voice_profile: v2-Key 'schreibrhythmus' bleibt in der Union (kanon. Ziel: satzarchitektur)."""
        assert "schreibrhythmus" in _EDITABLE_ROOT_KEYS["voice_profile"]

    def test_voice_profile_has_satzarchitektur(self):
        """voice_profile: 'satzarchitektur' muss enthalten sein (ersetzt stilprinzipien/schreibrhythmus)."""
        assert "satzarchitektur" in _EDITABLE_ROOT_KEYS["voice_profile"]

    def test_voice_profile_has_wortschatz(self):
        """voice_profile: 'wortschatz' muss enthalten sein (gleicher Key, p03.schema.json:83)."""
        assert "wortschatz" in _EDITABLE_ROOT_KEYS["voice_profile"]

    def test_audience_avatar_has_canonical_identitaet(self):
        """audience_avatar: 'identitaet' muss enthalten sein (ersetzt 'hauptperson', p04.schema.json:63)."""
        assert "identitaet" in _EDITABLE_ROOT_KEYS["audience_avatar"]

    def test_audience_avatar_has_canonical_content_trigger(self):
        """audience_avatar: 'content_trigger' muss enthalten sein (p04.schema.json:98)."""
        assert "content_trigger" in _EDITABLE_ROOT_KEYS["audience_avatar"]

    def test_audience_avatar_has_canonical_sprache_der_zielgruppe(self):
        """audience_avatar: 'sprache_der_zielgruppe' muss enthalten sein (p04.schema.json:121)."""
        assert "sprache_der_zielgruppe" in _EDITABLE_ROOT_KEYS["audience_avatar"]

    def test_audience_avatar_union_keeps_v2_hauptperson(self):
        """audience_avatar: v2-Key 'hauptperson' bleibt in der Union (Alt-Rows editierbar, Übergang)."""
        assert "hauptperson" in _EDITABLE_ROOT_KEYS["audience_avatar"]

    def test_audience_avatar_union_keeps_v2_kernschmerzen(self):
        """audience_avatar: v2-Key 'kernschmerzen' bleibt in der Union (Übergang)."""
        assert "kernschmerzen" in _EDITABLE_ROOT_KEYS["audience_avatar"]

    def test_audience_avatar_union_keeps_v2_transformation(self):
        """audience_avatar: v2-Key 'transformation' bleibt in der Union (Übergang)."""
        assert "transformation" in _EDITABLE_ROOT_KEYS["audience_avatar"]

    def test_audience_avatar_union_keeps_v2_einwaende(self):
        """audience_avatar: v2-Key 'einwaende' bleibt in der Union (Übergang)."""
        assert "einwaende" in _EDITABLE_ROOT_KEYS["audience_avatar"]

    def test_audience_avatar_union_keeps_v2_kaufmotive(self):
        """audience_avatar: v2-Key 'kaufmotive' bleibt in der Union (Übergang)."""
        assert "kaufmotive" in _EDITABLE_ROOT_KEYS["audience_avatar"]

    def test_audience_avatar_union_keeps_v2_sprachmuster(self):
        """audience_avatar: v2-Key 'sprachmuster' bleibt in der Union (Übergang)."""
        assert "sprachmuster" in _EDITABLE_ROOT_KEYS["audience_avatar"]

    def test_customer_context_unchanged(self):
        """customer_context: unverändert — kein Scope von Issue #29."""
        assert "kernbotschaft" in _EDITABLE_ROOT_KEYS["customer_context"]
        assert "werte" in _EDITABLE_ROOT_KEYS["customer_context"]


# ============================================================================
# 2. Tone-Extraktion — dialogue.py (kanonisch + Alt-Row-Fallback)
# ============================================================================


class TestExtractTone:
    """Tone wird kanonisch aus grundton.charakterisierung gelesen."""

    def test_canonical_row_grundton_charakterisierung(self):
        """Kanonische Row: liest grundton.charakterisierung korrekt."""
        vp = {"grundton": {"charakterisierung": "direkt, authentisch"}}
        assert _extract_tone(vp) == "direkt, authentisch"

    def test_canonical_row_prefers_grundton_over_tonalitaet(self):
        """Kanonische Row hat Vorrang vor Alt-Row-Fallback."""
        vp = {
            "grundton": {"charakterisierung": "kanonisch-korrekt"},
            "tonalitaet": {"grundton": "alt-v2-wert"},
        }
        assert _extract_tone(vp) == "kanonisch-korrekt"

    def test_alt_row_fallback_tonalitaet_grundton(self):
        """Alt-v2-Row: Fallback auf tonalitaet.grundton wenn kein grundton vorhanden."""
        vp = {"tonalitaet": {"grundton": "v2-tonalitaet-grundton"}}
        assert _extract_tone(vp) == "v2-tonalitaet-grundton"

    def test_tone_key_has_highest_priority(self):
        """Legacy 'tone'-Key hat höchste Priorität (vor grundton.charakterisierung)."""
        vp = {
            "tone": "legacy-tone",
            "grundton": {"charakterisierung": "canonical"},
            "tonalitaet": {"grundton": "v2"},
        }
        assert _extract_tone(vp) == "legacy-tone"

    def test_empty_profile_returns_default(self):
        """Leeres Profil → Default-Wert."""
        assert _extract_tone({}, default="standard") == "standard"

    def test_grundton_not_dict_skips_gracefully(self):
        """grundton ist kein dict → kein Fehler, Fallback greift."""
        vp = {"grundton": "nicht-ein-dict", "tonalitaet": {"grundton": "fallback"}}
        assert _extract_tone(vp) == "fallback"

    def test_grundton_empty_charakterisierung_falls_back(self):
        """grundton.charakterisierung ist leer → Alt-Fallback greift."""
        vp = {
            "grundton": {"charakterisierung": ""},
            "tonalitaet": {"grundton": "v2-fallback"},
        }
        assert _extract_tone(vp) == "v2-fallback"

    def test_canonical_keine_tonalitaet_kein_fallback_noetig(self):
        """Rein kanonische Row ohne Alt-Keys: funktioniert ohne Fehler."""
        vp = {
            "grundton": {"charakterisierung": "nur-kanonisch"},
            "satzarchitektur": {"laenge": "kurz"},
            "vermeidungsprofil": {"nie_sagen": ["bla"]},
        }
        assert _extract_tone(vp) == "nur-kanonisch"


# ============================================================================
# 3. Avoid-Extraktion — pipeline.py (kanonisch + Alt-Row-Fallback)
# ============================================================================


class TestExtractAvoid:
    """Vermeidungsprofil wird kanonisch aus vermeidungsprofil.nie_sagen gelesen."""

    def test_canonical_row_nie_sagen_strings(self):
        """Kanonische Row (string-items): gibt liste zurück."""
        vp = {"vermeidungsprofil": {"nie_sagen": ["buzzwords", "floskeln"]}}
        result = _extract_avoid(vp)
        assert result == ["buzzwords", "floskeln"]

    def test_canonical_row_nie_sagen_objects(self):
        """Kanonische Row (object-items mit item/grund): extrahiert 'item'-Feld."""
        vp = {
            "vermeidungsprofil": {
                "nie_sagen": [
                    {"item": "in der heutigen Zeit", "grund": "Floskel"},
                    {"item": "disruptiv", "grund": "Buzzword"},
                ]
            }
        }
        result = _extract_avoid(vp)
        assert result == ["in der heutigen Zeit", "disruptiv"]

    def test_canonical_row_prefers_nie_sagen_over_vermeidungsregeln(self):
        """Kanonische Row hat Vorrang über v2-Key vermeidungsregeln."""
        vp = {
            "vermeidungsprofil": {"nie_sagen": ["kanonisch"]},
            "vermeidungsregeln": ["v2-alt"],
        }
        result = _extract_avoid(vp)
        assert result == ["kanonisch"]

    def test_alt_row_fallback_vermeidungsregeln(self):
        """Alt-v2-Row ohne vermeidungsprofil: Fallback auf vermeidungsregeln."""
        vp = {"vermeidungsregeln": ["buzzword1", "buzzword2"]}
        result = _extract_avoid(vp)
        assert result == ["buzzword1", "buzzword2"]

    def test_topics_avoid_fallback(self):
        """topics_avoid-Key (Legacy) hat Vorrang vor vermeidungsregeln."""
        vp = {
            "topics_avoid": ["legacy-avoid"],
            "vermeidungsregeln": ["v2-alt"],
        }
        result = _extract_avoid(vp)
        assert result == ["legacy-avoid"]

    def test_empty_nie_sagen_falls_to_vermeidungsregeln(self):
        """Leeres nie_sagen ([] statt None) → kein Treffer → Fallback greift."""
        vp = {
            "vermeidungsprofil": {"nie_sagen": []},
            "vermeidungsregeln": ["v2-fallback"],
        }
        result = _extract_avoid(vp)
        assert result == ["v2-fallback"]

    def test_empty_profile_returns_none(self):
        """Komplett leeres Profil → None (kein Fehler)."""
        result = _extract_avoid({})
        assert result is None

    def test_vermeidungsprofil_not_dict_skips_gracefully(self):
        """vermeidungsprofil ist kein dict → kein Fehler, Fallback greift."""
        vp = {
            "vermeidungsprofil": "nicht-ein-dict",
            "vermeidungsregeln": ["v2-fallback"],
        }
        result = _extract_avoid(vp)
        assert result == ["v2-fallback"]

    def test_canonical_join_output_matches_pipeline_format(self):
        """Simuliert pipeline.py-Join: Komma-getrennte Ausgabe korrekt."""
        vp = {"vermeidungsprofil": {"nie_sagen": ["X", "Y", "Z"]}}
        items = _extract_avoid(vp)
        avoid_str = ", ".join(str(x) for x in items)
        assert avoid_str == "X, Y, Z"
