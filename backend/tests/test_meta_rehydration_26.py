"""
test_meta_rehydration_26.py — Tests für Issue #26: _meta-Rehydration (additive, sichere Teile).

Deckt ab:
  (a) agentur_id: meta mit/ohne agentur_id → korrekt + 'zb'-Fallback
  (b) prompt_version: aktueller-Prompt-SHA → 'p01-v1.0', unbekannter Hash → 'p01-legacy',
      leer → legacy, bereits-semantisch → durchgereicht
  (c) is_canonical: legacy bleibt False, p0X-v1.0 wird True — kein Flip für Alt-Rows
  (d) Migration 056: AST-Parse prüft revision='056', down_revision='055', nullable=True,
      server_default='zb', add_column/drop_column auf 'tenants'

INVARIANTE (getestet in TestPromptVersionResolution.test_invariante_alt_rows):
  Rows mit altem/unbekanntem Hash bleiben 'legacy' — kein is_canonical-Flip.

NOT-NULL-Kontrakt + historischer Hash-Backfill = Robert/DEFERIERT (separates ADR, Issue #26).

Ausführen (dep-frei via importlib):
    cd backend
    PYTHONPATH=. CONTENT_TRUTH_BASE_PATH=<repo>/content-truth \
        ../../.venv/bin/python -m pytest tests/test_meta_rehydration_26.py -q
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Modul-Loader (dep-frei, umgeht services/__init__.py → google.generativeai)
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).parent.parent
_ST_PATH = _BACKEND_DIR / "services" / "schema_transformer.py"
_CP_PATH = _BACKEND_DIR / "services" / "canonical_profiles.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_st = _load_module(_ST_PATH, "st_26")
_cp = _load_module(_CP_PATH, "cp_26")

_build_meta = _st._build_meta
_resolve_prompt_version = _st._resolve_prompt_version
_get_current_prompt_sha = _st._get_current_prompt_sha
_PROMPT_SHA_CACHE = _st._PROMPT_SHA_CACHE
is_canonical = _cp.is_canonical
build_canonical_meta = _st.build_canonical_meta

# Repo-Root content-truth-Verzeichnis (für SHA-Tests)
_CONTENT_TRUTH = _BACKEND_DIR.parent / "content-truth"


# ---------------------------------------------------------------------------
# (a) agentur_id-Verhalten in _build_meta
# ---------------------------------------------------------------------------


class TestAgenturId(unittest.TestCase):
    """_build_meta liefert korrekte agentur_id + 'zb'-Fallback."""

    def test_explicit_agentur_id_durchgereicht(self):
        meta = _build_meta("p01", {"agentur_id": "meine-agentur", "tenant_id": "t1"})
        self.assertEqual(meta["agentur_id"], "meine-agentur")

    def test_fallback_zb_wenn_nicht_gesetzt(self):
        meta = _build_meta("p01", {"tenant_id": "t1"})
        self.assertEqual(meta["agentur_id"], "zb")

    def test_fallback_zb_wenn_leer(self):
        meta = _build_meta("p01", {"agentur_id": "", "tenant_id": "t1"})
        self.assertEqual(meta["agentur_id"], "zb")

    def test_fallback_zb_wenn_none(self):
        meta = _build_meta("p01", {"agentur_id": None, "tenant_id": "t1"})
        self.assertEqual(meta["agentur_id"], "zb")

    def test_whitespace_agentur_id_wird_getrimmt(self):
        meta = _build_meta("p01", {"agentur_id": "  zb2  ", "tenant_id": "t1"})
        self.assertEqual(meta["agentur_id"], "zb2")

    def test_whitespace_only_agentur_id_fallback_zb(self):
        meta = _build_meta("p01", {"agentur_id": "   ", "tenant_id": "t1"})
        self.assertEqual(meta["agentur_id"], "zb")


# ---------------------------------------------------------------------------
# (b) prompt_version-Auflösung in _resolve_prompt_version
# ---------------------------------------------------------------------------


class TestPromptVersionResolution(unittest.TestCase):
    """_resolve_prompt_version: SHA-Match → v1.0, unbekannt → legacy."""

    def setUp(self):
        # SHA-Cache leeren, damit Tests isoliert laufen
        _PROMPT_SHA_CACHE.clear()

    def test_leer_ergibt_legacy(self):
        result = _resolve_prompt_version("p01", "")
        self.assertEqual(result, "p01-legacy")

    def test_none_ergibt_legacy(self):
        # _resolve_prompt_version erwartet str; None-Pfad läuft über _build_meta
        result = _resolve_prompt_version("p01", "")
        self.assertEqual(result, "p01-legacy")

    def test_bereits_semantisch_p0x_wird_durchgereicht(self):
        result = _resolve_prompt_version("p01", "p01-v1.0")
        self.assertEqual(result, "p01-v1.0")

    def test_bereits_semantisch_p03(self):
        result = _resolve_prompt_version("p03", "p03-v2.1")
        self.assertEqual(result, "p03-v2.1")

    def test_bereits_semantisch_values(self):
        result = _resolve_prompt_version("values", "values-v1.0")
        self.assertEqual(result, "values-v1.0")

    def test_unbekannter_hash_ergibt_legacy(self):
        result = _resolve_prompt_version("p01", "deadbeef" * 8)
        self.assertEqual(result, "p01-legacy")

    def test_aktueller_sha_p01_ergibt_v1_0(self):
        """SHA des aktuellen P01-Prompt-Files → 'p01-v1.0'."""
        p01_file = _CONTENT_TRUTH / "prompts" / "P01-kundenkontext-extraktion.md"
        if not p01_file.exists():
            self.skipTest(f"Prompt-File nicht gefunden: {p01_file}")
        sha = hashlib.sha256(p01_file.read_bytes()).hexdigest()
        env = {"CONTENT_TRUTH_BASE_PATH": str(_CONTENT_TRUTH)}
        with patch.dict(os.environ, env):
            _PROMPT_SHA_CACHE.clear()
            result = _resolve_prompt_version("p01", sha)
        self.assertEqual(result, "p01-v1.0")

    def test_aktueller_sha_p03_ergibt_v1_0(self):
        """SHA des aktuellen P03-Prompt-Files → 'p03-v1.0'."""
        p03_file = _CONTENT_TRUTH / "prompts" / "P03-voice-analyse.md"
        if not p03_file.exists():
            self.skipTest(f"Prompt-File nicht gefunden: {p03_file}")
        sha = hashlib.sha256(p03_file.read_bytes()).hexdigest()
        env = {"CONTENT_TRUTH_BASE_PATH": str(_CONTENT_TRUTH)}
        with patch.dict(os.environ, env):
            _PROMPT_SHA_CACHE.clear()
            result = _resolve_prompt_version("p03", sha)
        self.assertEqual(result, "p03-v1.0")

    def test_aktueller_sha_p04_ergibt_v1_0(self):
        """SHA des aktuellen P04-Prompt-Files → 'p04-v1.0'."""
        p04_file = _CONTENT_TRUTH / "prompts" / "P04-kundenavatar-vertiefung.md"
        if not p04_file.exists():
            self.skipTest(f"Prompt-File nicht gefunden: {p04_file}")
        sha = hashlib.sha256(p04_file.read_bytes()).hexdigest()
        env = {"CONTENT_TRUTH_BASE_PATH": str(_CONTENT_TRUTH)}
        with patch.dict(os.environ, env):
            _PROMPT_SHA_CACHE.clear()
            result = _resolve_prompt_version("p04", sha)
        self.assertEqual(result, "p04-v1.0")

    def test_unbekannter_prompt_key_failopen(self):
        """Unbekannter Prompt-Key (kein Eintrag in _PROMPT_RELATIVE_PATHS) → legacy."""
        result = _resolve_prompt_version("p99", "deadbeef" * 8)
        self.assertEqual(result, "p99-legacy")

    def test_invariante_alt_rows(self):
        """INVARIANTE: Alter/falscher Hash bleibt 'legacy', kein is_canonical-Flip.

        Simuliert eine Alt-Row: Hash aus P01-SHA mit einem Byte geändert
        → soll NICHT als kanonisch erkannt werden.
        """
        p01_file = _CONTENT_TRUTH / "prompts" / "P01-kundenkontext-extraktion.md"
        if not p01_file.exists():
            self.skipTest(f"Prompt-File nicht gefunden: {p01_file}")
        real_sha = hashlib.sha256(p01_file.read_bytes()).hexdigest()
        # Einen Buchstaben kippen → falscher Hash
        wrong_sha = ("0" if real_sha[0] != "0" else "1") + real_sha[1:]
        env = {"CONTENT_TRUTH_BASE_PATH": str(_CONTENT_TRUTH)}
        with patch.dict(os.environ, env):
            _PROMPT_SHA_CACHE.clear()
            pv = _resolve_prompt_version("p01", wrong_sha)
        self.assertEqual(pv, "p01-legacy", "Falscher Hash muss 'legacy' bleiben")
        # is_canonical muss False bleiben
        payload = {"_meta": {"prompt_version": pv, "agentur_id": "zb",
                              "kunde_id": "test", "model": "x", "generated_at": "now"}}
        self.assertFalse(is_canonical(payload), "Alt-Row darf nicht als kanonisch gelten")

    def test_sha_cache_wird_genutzt(self):
        """Zweiter Aufruf mit gleichem Key liest aus Cache (kein File-IO)."""
        p01_file = _CONTENT_TRUTH / "prompts" / "P01-kundenkontext-extraktion.md"
        if not p01_file.exists():
            self.skipTest(f"Prompt-File nicht gefunden: {p01_file}")
        sha = hashlib.sha256(p01_file.read_bytes()).hexdigest()
        env = {"CONTENT_TRUTH_BASE_PATH": str(_CONTENT_TRUTH)}
        with patch.dict(os.environ, env):
            _PROMPT_SHA_CACHE.clear()
            _resolve_prompt_version("p01", sha)
            # Cache muss nun befüllt sein
            self.assertIn("p01", _PROMPT_SHA_CACHE)
            cached_sha = _PROMPT_SHA_CACHE["p01"]
        self.assertEqual(cached_sha, sha)

    def test_prompt_file_nicht_lesbar_failopen(self):
        """Nicht-existentes CONTENT_TRUTH_BASE_PATH → fail-open → 'legacy'."""
        env = {"CONTENT_TRUTH_BASE_PATH": "/nicht-existentes-verzeichnis-xyzzy"}
        with patch.dict(os.environ, env):
            _PROMPT_SHA_CACHE.clear()
            result = _resolve_prompt_version("p01", "beliebiger-hash")
        self.assertEqual(result, "p01-legacy")


# ---------------------------------------------------------------------------
# (c) is_canonical-Verhalten: legacy vs. kanonisch
# ---------------------------------------------------------------------------


class TestIsCanonical(unittest.TestCase):
    """is_canonical: legacy bleibt False, p0X-v1.0 → True, kein Flip für Alt-Rows."""

    def _payload(self, pv: str) -> dict:
        return {
            "_meta": {
                "prompt_version": pv,
                "agentur_id": "zb",
                "kunde_id": "test",
                "model": "x",
                "generated_at": "2026-01-01T00:00:00Z",
            }
        }

    def test_p01_v1_0_kanonisch(self):
        self.assertTrue(is_canonical(self._payload("p01-v1.0")))

    def test_p03_v1_0_kanonisch(self):
        self.assertTrue(is_canonical(self._payload("p03-v1.0")))

    def test_p04_v1_0_kanonisch(self):
        self.assertTrue(is_canonical(self._payload("p04-v1.0")))

    def test_p01_legacy_nicht_kanonisch(self):
        self.assertFalse(is_canonical(self._payload("p01-legacy")))

    def test_p03_legacy_nicht_kanonisch(self):
        self.assertFalse(is_canonical(self._payload("p03-legacy")))

    def test_p04_legacy_nicht_kanonisch(self):
        self.assertFalse(is_canonical(self._payload("p04-legacy")))

    def test_leere_prompt_version_nicht_kanonisch(self):
        self.assertFalse(is_canonical(self._payload("")))

    def test_kein_meta_nicht_kanonisch(self):
        self.assertFalse(is_canonical({"daten": "xyz"}))

    def test_none_nicht_kanonisch(self):
        self.assertFalse(is_canonical(None))

    def test_values_v1_0_kanonisch(self):
        self.assertTrue(is_canonical(self._payload("values-v1.0")))

    def test_alt_row_hash_als_version_nicht_kanonisch(self):
        """Ein roher SHA-256-Hash als prompt_version ist NICHT kanonisch."""
        fake_hash = "a" * 64
        self.assertFalse(is_canonical(self._payload(fake_hash)))

    def test_build_canonical_meta_erzeugt_kanonische_version(self):
        """build_canonical_meta mit key='p01' → is_canonical=True."""
        meta = build_canonical_meta(
            "p01",
            tenant_id="t-test",
            model="test-model",
            generated_at="2026-01-01T00:00:00Z",
        )
        payload = {"_meta": meta}
        self.assertTrue(is_canonical(payload), f"meta={meta}")


# ---------------------------------------------------------------------------
# (d) Migration 056 — AST-Parse
# ---------------------------------------------------------------------------


class TestMigration056(unittest.TestCase):
    """Prüft die Migration-Datei ohne DB-Zugriff via AST."""

    _MIGRATION_PATH = (
        _BACKEND_DIR / "alembic" / "versions" / "056_tenant_agentur_id.py"
    )

    def _parse(self) -> ast.Module:
        if not self._MIGRATION_PATH.exists():
            self.fail(f"Migration nicht gefunden: {self._MIGRATION_PATH}")
        return ast.parse(self._MIGRATION_PATH.read_text(encoding="utf-8"))

    def _get_assignments(self, tree: ast.Module) -> dict:
        """Extrahiert Modul-Level-Zuweisungen als {name: value_str}."""
        result = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        try:
                            result[target.id] = ast.literal_eval(node.value)
                        except (ValueError, TypeError):
                            pass
        return result

    def test_revision_korrekt(self):
        tree = self._parse()
        assigns = self._get_assignments(tree)
        self.assertEqual(assigns.get("revision"), "056")

    def test_down_revision_korrekt(self):
        tree = self._parse()
        assigns = self._get_assignments(tree)
        self.assertEqual(assigns.get("down_revision"), "055")

    def test_upgrade_enthaelt_add_column(self):
        source = self._MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("add_column", source, "upgrade() muss add_column enthalten")

    def test_downgrade_enthaelt_drop_column(self):
        source = self._MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("drop_column", source, "downgrade() muss drop_column enthalten")

    def test_tabelle_tenants(self):
        source = self._MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn('"tenants"', source, "Migration muss auf Tabelle 'tenants' operieren")

    def test_spalte_agentur_id(self):
        source = self._MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn('"agentur_id"', source, "Spaltenname 'agentur_id' muss vorkommen")

    def test_nullable_true(self):
        source = self._MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("nullable=True", source, "Spalte muss nullable=True sein")

    def test_server_default_zb(self):
        source = self._MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn('server_default="zb"', source, "server_default muss 'zb' sein")

    def test_kein_alembic_upgrade_execute(self):
        """Sicherheitscheck: Migration führt kein alembic upgrade / op.execute aus."""
        source = self._MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertNotIn("op.execute(", source, "Keine op.execute() in dieser Migration")


if __name__ == "__main__":
    unittest.main()
