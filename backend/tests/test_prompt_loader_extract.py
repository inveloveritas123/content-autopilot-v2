"""
Tests fuer die robuste _extract_section / _extract_system_prompt / _extract_user_prompt
Implementierung in prompt_loader.py (Ansatz B).

Prueft:
1. Echte Prompt-Dateien (P01, P03, P04, P12, P12b, P12c):
   - system_prompt NICHT trunkiert (Laenge > 500 UND enthaelt Inhalt spaeterer ##-Abschnitte)
   - Kein nackter ``` am Anfang/Ende des extrahierten Texts
2. Fence-Bereinigung (_strip_outer_fence)
3. Synthetische Unit-Tests fuer _extract_section mit Mini-Strings:
   - Mehrere ## im System-Block
   - Kein User-Prompt vorhanden
   - Unbalancierter Fence

Import-Strategie: services/__init__.py wird NICHT getriggert (google-Import vermeiden).
Module werden direkt per importlib.util geladen.
"""

import importlib
import importlib.util
import os
import sys
import types
import unittest

# ---------------------------------------------------------------------------
# Hilfsfunktion: Modul direkt aus Dateipfad laden (umgeht __init__.py)
# ---------------------------------------------------------------------------


def _load_module_from_file(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Basis-Verzeichnis des Backends
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_REPO_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))
_CONTENT_TRUTH = os.environ.get(
    "CONTENT_TRUTH_BASE_PATH",
    os.path.join(_REPO_ROOT, "content-truth"),
)

# Stubs fuer google / anthropic (falls noch nicht in sys.modules)
for _pkg in ("google", "google.generativeai", "anthropic", "httpx"):
    if _pkg not in sys.modules:
        _m = types.ModuleType(_pkg)
        sys.modules[_pkg] = _m

# config laden
_load_module_from_file("config", os.path.join(_BACKEND_DIR, "config.py"))

# brand_voice_storage laden
_load_module_from_file(
    "services.brand_voice_storage",
    os.path.join(_BACKEND_DIR, "services", "brand_voice_storage.py"),
)

# local_fs_storage laden
_load_module_from_file(
    "services.local_fs_storage",
    os.path.join(_BACKEND_DIR, "services", "local_fs_storage.py"),
)

# prompt_loader laden
_load_module_from_file(
    "services.prompt_loader",
    os.path.join(_BACKEND_DIR, "services", "prompt_loader.py"),
)

from services.local_fs_storage import LocalFsStorageAdapter
from services.prompt_loader import (
    _extract_section,
    _strip_outer_fence,
)

# ---------------------------------------------------------------------------
# Hilfsfunktion: echte Prompt-Datei laden
# ---------------------------------------------------------------------------


def _load_prompt(filename: str) -> str:
    adapter = LocalFsStorageAdapter(base_dir=_CONTENT_TRUTH)
    raw = adapter.read(f"prompts/{filename}")
    return raw.decode("utf-8")


# ---------------------------------------------------------------------------
# Tests: Echte Prompt-Dateien — System-Prompt nicht trunkiert
# ---------------------------------------------------------------------------


class TestRealPromptFiles(unittest.TestCase):
    """Prueft echte Prompt-Dateien gegen Trunkierung und Fence-Artefakte."""

    # --- P01 ---

    def test_p01_system_prompt_length_above_500(self):
        content = _load_prompt("P01-kundenkontext-extraktion.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertGreater(
            len(sys_p), 500, f"P01 system_prompt zu kurz: {len(sys_p)} Zeichen (erwartet >500)"
        )

    def test_p01_system_prompt_contains_later_section(self):
        """'## Extraktions-Kategorien' liegt im System-Prompt-Block — muss enthalten sein."""
        content = _load_prompt("P01-kundenkontext-extraktion.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertIn(
            "Extraktions-Kategorien",
            sys_p,
            "P01 system_prompt enthaelt nicht 'Extraktions-Kategorien' — trunkiert?",
        )

    def test_p01_system_prompt_contains_qualitaets_check(self):
        """'## Qualitaets-Check' liegt im System-Prompt-Block."""
        content = _load_prompt("P01-kundenkontext-extraktion.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertIn(
            "Qualitäts-Check",
            sys_p,
            "P01 system_prompt enthaelt nicht 'Qualitaets-Check' — trunkiert?",
        )

    def test_p01_system_prompt_no_naked_fence_start(self):
        content = _load_prompt("P01-kundenkontext-extraktion.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertFalse(
            sys_p.startswith("```"),
            f"P01 system_prompt beginnt mit ``` (Fence nicht bereinigt): {sys_p[:80]!r}",
        )

    def test_p01_system_prompt_no_naked_fence_end(self):
        content = _load_prompt("P01-kundenkontext-extraktion.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertFalse(
            sys_p.endswith("```"), "P01 system_prompt endet mit ``` (Fence nicht bereinigt)"
        )

    def test_p01_user_prompt_not_empty(self):
        content = _load_prompt("P01-kundenkontext-extraktion.md")
        usr_p = _extract_section(content, "User-Prompt")
        self.assertGreater(len(usr_p), 0, "P01 user_prompt ist leer")

    # --- P03 ---

    def test_p03_system_prompt_length_above_500(self):
        content = _load_prompt("P03-voice-analyse.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertGreater(len(sys_p), 500, f"P03 system_prompt zu kurz: {len(sys_p)} Zeichen")

    def test_p03_system_prompt_contains_later_section(self):
        """'## Output-Felder' liegt nach ## System-Prompt — muss enthalten sein."""
        content = _load_prompt("P03-voice-analyse.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertIn(
            "Output-Felder", sys_p, "P03 system_prompt enthaelt nicht 'Output-Felder' — trunkiert?"
        )

    def test_p03_system_prompt_no_naked_fence(self):
        content = _load_prompt("P03-voice-analyse.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertFalse(
            sys_p.startswith("```"), f"P03 system_prompt beginnt mit ```: {sys_p[:80]!r}"
        )
        self.assertFalse(sys_p.endswith("```"), "P03 system_prompt endet mit ```")

    # --- P04 ---

    def test_p04_system_prompt_length_above_500(self):
        content = _load_prompt("P04-kundenavatar-vertiefung.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertGreater(len(sys_p), 500, f"P04 system_prompt zu kurz: {len(sys_p)} Zeichen")

    def test_p04_system_prompt_contains_later_section(self):
        """'## Output-Felder' liegt nach ## System-Prompt in P04."""
        content = _load_prompt("P04-kundenavatar-vertiefung.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertIn(
            "Output-Felder", sys_p, "P04 system_prompt enthaelt nicht 'Output-Felder' — trunkiert?"
        )

    def test_p04_system_prompt_no_naked_fence(self):
        content = _load_prompt("P04-kundenavatar-vertiefung.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertFalse(
            sys_p.startswith("```"), f"P04 system_prompt beginnt mit ```: {sys_p[:80]!r}"
        )

    # --- P12 ---

    def test_p12_system_prompt_length_above_500(self):
        content = _load_prompt("P12-post-generierung.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertGreater(
            len(sys_p), 500, f"P12 system_prompt zu kurz: {len(sys_p)} Zeichen (alter Bug: ~338)"
        )

    def test_p12_system_prompt_contains_ki_signale_section(self):
        """'## Ablauf' oder 'KI-Signale' liegt nach dem ersten ##-Heading im System-Block."""
        content = _load_prompt("P12-post-generierung.md")
        sys_p = _extract_section(content, "System-Prompt")
        # Der Block muss weit über den ersten ## hinausgehen
        self.assertTrue(
            "KI-Signale" in sys_p or "Ablauf" in sys_p,
            "P12 system_prompt enthaelt weder 'KI-Signale' noch 'Ablauf' — trunkiert?",
        )

    def test_p12_system_prompt_no_naked_fence(self):
        content = _load_prompt("P12-post-generierung.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertFalse(
            sys_p.startswith("```"), f"P12 system_prompt beginnt mit ```: {sys_p[:80]!r}"
        )
        self.assertFalse(sys_p.endswith("```"), "P12 system_prompt endet mit ```")

    def test_p12_system_prompt_substantially_longer_than_old_bug(self):
        """Stellt sicher, dass der alte Trunkierungs-Bug (338 Zeichen) behoben ist."""
        content = _load_prompt("P12-post-generierung.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertGreater(
            len(sys_p),
            1000,
            f"P12 system_prompt wahrscheinlich noch trunkiert: {len(sys_p)} Zeichen",
        )

    # --- P12b ---

    def test_p12b_system_prompt_length_above_500(self):
        content = _load_prompt("P12b-post-optimierung.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertGreater(len(sys_p), 500, f"P12b system_prompt zu kurz: {len(sys_p)} Zeichen")

    def test_p12b_system_prompt_contains_later_section(self):
        """'## Dein Output' liegt nach den fruehen ## Abschnitten in P12b."""
        content = _load_prompt("P12b-post-optimierung.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertIn(
            "Dein Output", sys_p, "P12b system_prompt enthaelt nicht 'Dein Output' — trunkiert?"
        )

    def test_p12b_system_prompt_no_naked_fence(self):
        content = _load_prompt("P12b-post-optimierung.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertFalse(
            sys_p.startswith("```"), f"P12b system_prompt beginnt mit ```: {sys_p[:80]!r}"
        )

    # --- P12c ---

    def test_p12c_system_prompt_not_empty(self):
        """P12c hat kein ## Übersicht usw. — System-Prompt steht direkt am Anfang."""
        content = _load_prompt("P12c-carousel-generator.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertGreater(len(sys_p), 0, "P12c system_prompt ist leer")

    def test_p12c_system_prompt_no_naked_fence(self):
        content = _load_prompt("P12c-carousel-generator.md")
        sys_p = _extract_section(content, "System-Prompt")
        self.assertFalse(
            sys_p.startswith("```"), f"P12c system_prompt beginnt mit ```: {sys_p[:80]!r}"
        )


# ---------------------------------------------------------------------------
# Tests: _strip_outer_fence
# ---------------------------------------------------------------------------


class TestStripOuterFence(unittest.TestCase):
    """Unit-Tests fuer _strip_outer_fence."""

    def test_balanced_fence_removed(self):
        block = "```\nHallo Welt\n```"
        self.assertEqual(_strip_outer_fence(block), "Hallo Welt")

    def test_balanced_fence_with_lang_removed(self):
        block = "```python\nprint('hello')\n```"
        self.assertEqual(_strip_outer_fence(block), "print('hello')")

    def test_no_fence_unchanged(self):
        block = "Kein Fence hier"
        self.assertEqual(_strip_outer_fence(block), "Kein Fence hier")

    def test_unbalanced_leading_fence_removed(self):
        block = "```\nInnerer Text ohne Abschluss"
        result = _strip_outer_fence(block)
        self.assertFalse(
            result.startswith("```"), f"Fuehrender Fence nicht entfernt: {result[:50]!r}"
        )
        self.assertIn("Innerer Text", result)

    def test_internal_fences_preserved(self):
        """Interne, balancierte Fences innerhalb des Texts bleiben erhalten."""
        block = '```\nBeschreibung.\n\n```json\n{"a": 1}\n```\n\nMehr Text.\n```'
        result = _strip_outer_fence(block)
        self.assertIn("```json", result, "Interner Fence wurde faelschlicherweise entfernt")
        self.assertIn('{"a": 1}', result)

    def test_empty_block(self):
        self.assertEqual(_strip_outer_fence(""), "")

    def test_only_fence_markers(self):
        block = "```\n```"
        result = _strip_outer_fence(block)
        # Nach Entfernung bleibt leerer String oder leere Zeile
        self.assertEqual(result.strip(), "")


# ---------------------------------------------------------------------------
# Tests: Synthetische Unit-Tests fuer _extract_section
# ---------------------------------------------------------------------------


class TestExtractSectionSynthetic(unittest.TestCase):
    """Synthetische Tests mit Mini-Strings."""

    # --- System-Prompt: mehrere ## im Block ---

    def test_multiple_hashes_in_system_block_included(self):
        """Zwischenliegende ## Abschnitte gehoeren zum System-Prompt."""
        content = (
            "# Titel\n\n"
            "## System-Prompt\n\n"
            "```\n"
            "Erster Absatz.\n\n"
            "## Deine Aufgabe\n\n"
            "Tu dies und das.\n\n"
            "## Output-Format\n\n"
            "JSON bitte.\n"
            "```\n\n"
            "## User-Prompt\n\n"
            "```\nMach was.\n```\n"
        )
        sys_p = _extract_section(content, "System-Prompt")
        self.assertIn("Deine Aufgabe", sys_p, "## Deine Aufgabe fehlt im System-Prompt")
        self.assertIn("Output-Format", sys_p, "## Output-Format fehlt im System-Prompt")
        # Kein Fence-Marker am Anfang
        self.assertFalse(sys_p.startswith("```"))

    def test_system_prompt_ends_at_user_prompt(self):
        """System-Prompt endet genau vor ## User-Prompt."""
        content = (
            "## System-Prompt\n\n"
            "```\nSystem-Inhalt.\n```\n\n"
            "## User-Prompt\n\n"
            "```\nUser-Inhalt.\n```\n"
        )
        sys_p = _extract_section(content, "System-Prompt")
        self.assertIn("System-Inhalt", sys_p)
        self.assertNotIn("User-Inhalt", sys_p)

    # --- Kein User-Prompt vorhanden ---

    def test_no_user_prompt_returns_empty_string(self):
        """Falls kein ## User-Prompt, user_prompt ist leerer String."""
        content = "## System-Prompt\n\n" "```\nNur System.\n```\n\n" "## Weiteres\n\nNoch mehr.\n"
        usr_p = _extract_section(content, "User-Prompt")
        self.assertEqual(usr_p, "", f"user_prompt sollte leer sein, bekam: {usr_p!r}")

    def test_system_prompt_until_eof_if_no_user_prompt(self):
        """System-Prompt laeuft bis Dateiende wenn kein ## User-Prompt folgt."""
        content = (
            "## System-Prompt\n\n" "```\n" "Teil A.\n\n" "## Abschnitt B\n\n" "Teil B.\n" "```\n"
        )
        sys_p = _extract_section(content, "System-Prompt")
        self.assertIn("Teil A", sys_p)
        self.assertIn("Teil B", sys_p)

    # --- Unbalancierter Fence ---

    def test_unbalanced_opening_fence_stripped(self):
        """Nur oeffnender Fence ohne Abschluss wird entfernt."""
        content = (
            "## System-Prompt\n\n"
            "```\n"
            "Inhalt ohne Abschluss-Fence.\n\n"
            "## User-Prompt\n\n"
            "Hier.\n"
        )
        sys_p = _extract_section(content, "System-Prompt")
        self.assertFalse(sys_p.startswith("```"), f"Fence-Marker nicht entfernt: {sys_p[:80]!r}")
        self.assertIn("Inhalt ohne Abschluss", sys_p)

    def test_fully_missing_system_prompt_section(self):
        """Falls ## System-Prompt fehlt, leerer String."""
        content = "# Kein System-Prompt\n\n## User-Prompt\n\nHier steht was.\n"
        sys_p = _extract_section(content, "System-Prompt")
        self.assertEqual(sys_p, "")

    # --- User-Prompt: Ueberschrift mit MODE-Suffix wird erkannt ---

    def test_user_prompt_mit_mode_suffix_wird_extrahiert(self):
        """'## User-Prompt: MODE OPENER' MUSS greifen.

        Umgeschrieben am 04.08.2026. Vorher stand hier das Gegenteil — und
        genau diese Erwartung war der stille Totalausfall: `_extract_system_prompt`
        beendete den System-Block an `^## User-Prompt\\b` (traf also den Suffix),
        `_extract_user_prompt` verlangte `^## User-Prompt[ \\t]*$` (traf ihn nicht).
        Ergebnis: leerer User-Prompt, Rueckfall auf einen 789-Byte-Stummel,
        gemeldet als WARNING pro Aufruf, die niemand liest.

        Der Test bewacht jetzt die Symmetrie: was den System-Block beendet, muss
        den User-Block beginnen.
        """
        content = (
            "## System-Prompt\n\n"
            "```\nSystem.\n```\n\n"
            "## User-Prompt: MODE RESPONSE\n\n"
            "```\nOpener.\n```\n"
        )
        usr_p = _extract_section(content, "User-Prompt")
        self.assertEqual(usr_p, "Opener.")

    def test_mode_suffix_landet_nicht_im_text(self):
        """Der Suffix selbst gehoert zur Ueberschrift, nicht zum Prompt-Text."""
        content = "## System-Prompt\n\nSystem.\n\n## User-Prompt: MODE RESPONSE\n\nHier der Text.\n"
        usr_p = _extract_section(content, "User-Prompt")
        self.assertNotIn("MODE RESPONSE", usr_p)
        self.assertEqual(usr_p, "Hier der Text.")

    def test_system_und_user_teilen_sich_dieselbe_grenze(self):
        """Kein Text darf zwischen den beiden Extraktoren verschwinden.

        Die Asymmetrie liess einen ganzen Block ins Nichts fallen: er war weder
        System- noch User-Prompt. Dieser Test faengt jede kuenftige Variante davon.
        """
        content = (
            "## System-Prompt\n\nSystem-Teil.\n\n## User-Prompt: MODE RESPONSE\n\nUser-Teil.\n"
        )
        sys_p = _extract_section(content, "System-Prompt")
        usr_p = _extract_section(content, "User-Prompt")
        self.assertIn("System-Teil", sys_p)
        self.assertNotIn("User-Teil", sys_p)
        self.assertIn("User-Teil", usr_p)

    def test_user_prompt_exact_match_extracted(self):
        """Exakter ## User-Prompt wird korrekt extrahiert."""
        content = (
            "## System-Prompt\n\n"
            "```\nSystem.\n```\n\n"
            "## User-Prompt\n\n"
            "```\nUser-Text hier.\n```\n\n"
            "## Naechste Sektion\n\nNachher.\n"
        )
        usr_p = _extract_section(content, "User-Prompt")
        self.assertIn("User-Text hier", usr_p)
        self.assertNotIn("Nachher", usr_p)

    # --- Fence im System-Prompt-Inhalt: interne balancierte Fences bleiben ---

    def test_internal_balanced_fence_preserved_in_system(self):
        """Interne Code-Beispiele im System-Prompt bleiben erhalten."""
        content = (
            "## System-Prompt\n\n"
            "```\n"
            "Erklaerung.\n\n"
            "Beispiel:\n"
            "```json\n"
            '{"key": "value"}\n'
            "```\n\n"
            "Ende der Erklaerung.\n"
            "```\n\n"
            "## User-Prompt\n\nUser.\n"
        )
        sys_p = _extract_section(content, "System-Prompt")
        self.assertIn(
            "```json", sys_p, "Interner json-Fence wurde entfernt (sollte erhalten bleiben)"
        )
        self.assertIn('"key"', sys_p)

    # --- Generischer Fallback fuer andere Sektionsnamen ---

    def test_generic_section_fallback(self):
        """Generischer Fallback fuer nicht-System/User Sektionen."""
        content = "## Uebersicht\n\nHier steht was.\n\n" "## Naechste Sektion\n\nNoch mehr.\n"
        result = _extract_section(content, "Uebersicht")
        self.assertIn("Hier steht was", result)
        self.assertNotIn("Noch mehr", result)


# ---------------------------------------------------------------------------
# Tests: Alle PROMPT_PATHS erreichbar und system_prompt > 0 (ausser bekannte Ausnahmen)
# ---------------------------------------------------------------------------


class TestAllPromptPathsHealthy(unittest.TestCase):
    """Schnell-Check: alle PROMPT_PATHS lesbar, system_prompt nicht leer."""

    # Prompts ohne ## System-Prompt Sektion (rules-Dateien, P17)
    _NO_SYSTEM_EXPECTED = {"fragenkatalog", "hookmaster", "P17"}

    def _load(self, rel_path: str) -> str:
        adapter = LocalFsStorageAdapter(base_dir=_CONTENT_TRUTH)
        raw = adapter.read(rel_path)
        return raw.decode("utf-8")

    def test_all_prompt_files_readable(self):
        from services.prompt_loader import PROMPT_PATHS

        for key, path in PROMPT_PATHS.items():
            with self.subTest(key=key):
                content = self._load(path)
                self.assertGreater(len(content), 0, f"{key}: Datei ist leer")

    def test_all_prompts_have_system_prompt_or_are_known_exceptions(self):
        from services.prompt_loader import PROMPT_PATHS

        for key, path in PROMPT_PATHS.items():
            with self.subTest(key=key):
                if key in self._NO_SYSTEM_EXPECTED:
                    continue
                content = self._load(path)
                sys_p = _extract_section(content, "System-Prompt")
                self.assertGreater(
                    len(sys_p),
                    0,
                    f"{key}: system_prompt ist leer (kein ## System-Prompt in {path})",
                )

    def test_no_prompt_has_naked_fence_in_system(self):
        from services.prompt_loader import PROMPT_PATHS

        for key, path in PROMPT_PATHS.items():
            with self.subTest(key=key):
                content = self._load(path)
                sys_p = _extract_section(content, "System-Prompt")
                if not sys_p:
                    continue
                self.assertFalse(
                    sys_p.startswith("```"),
                    f"{key}: system_prompt beginnt mit ``` (Fence-Artefakt)",
                )
                self.assertFalse(
                    sys_p.endswith("```"), f"{key}: system_prompt endet mit ``` (Fence-Artefakt)"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
