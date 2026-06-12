"""
Tests fuer LocalFsStorageAdapter.

Deckt ab: read, write, exists, stat, list, Path-Traversal-Abwehr
und Integration mit PromptLoader / _extract_section fuer P01.

Import-Strategie: services/__init__.py zieht eine lange Kette von
Heavy-Dependencies (sqlalchemy, google-generativeai, celery ...) nach sich.
Diese sind im leichten Test-venv nicht installiert. Wir laden die
benoetigten Module deshalb direkt per importlib, ohne das __init__.py
des packages zu triggern.
"""
import importlib
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from datetime import timezone
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Hilfsfunktion: Modul direkt aus Dateipfad laden (umgeht __init__.py)
# ---------------------------------------------------------------------------

def _load_module_from_file(module_name: str, file_path: str) -> types.ModuleType:
    """Laedt ein Python-Modul direkt aus einem Dateipfad in sys.modules."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Basis-Verzeichnis des Backends (eine Ebene ueber diesem Test-File)
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Minimale Stubs damit pydantic-settings / config.py ohne .env-Datei laeuft
import types as _types
for _pkg in ("google", "google.generativeai", "anthropic"):
    if _pkg not in sys.modules:
        _m = _types.ModuleType(_pkg)
        sys.modules[_pkg] = _m

# config direkt laden (benoetigt nur pydantic-settings, das im venv ist)
_config = _load_module_from_file(
    "config",
    os.path.join(_BACKEND_DIR, "config.py"),
)

# brand_voice_storage direkt laden (benoetigt httpx + config)
_bvs = _load_module_from_file(
    "services.brand_voice_storage",
    os.path.join(_BACKEND_DIR, "services", "brand_voice_storage.py"),
)

# local_fs_storage direkt laden
_lfs = _load_module_from_file(
    "services.local_fs_storage",
    os.path.join(_BACKEND_DIR, "services", "local_fs_storage.py"),
)

# prompt_loader direkt laden (benoetigt brand_voice_storage + config)
_pl = _load_module_from_file(
    "services.prompt_loader",
    os.path.join(_BACKEND_DIR, "services", "prompt_loader.py"),
)


class TestLocalFsStorageAdapter(unittest.TestCase):
    """Einheitstests fuer alle Methoden des LocalFsStorageAdapter."""

    def setUp(self):
        # Frisches temp-Verzeichnis fuer jeden Test
        self._tmpdir = tempfile.mkdtemp()
        from services.local_fs_storage import LocalFsStorageAdapter
        self.adapter = LocalFsStorageAdapter(base_dir=self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # exists
    # ------------------------------------------------------------------

    def test_exists_false_for_missing_file(self):
        self.assertFalse(self.adapter.exists("nonexistent.txt"))

    def test_exists_true_after_write(self):
        self.adapter.write("hello.txt", b"inhalt")
        self.assertTrue(self.adapter.exists("hello.txt"))

    # ------------------------------------------------------------------
    # write + read
    # ------------------------------------------------------------------

    def test_write_and_read_roundtrip(self):
        data = "Hallo Welt — UTF-8 öäü".encode("utf-8")
        self.adapter.write("test/datei.md", data)
        result = self.adapter.read("test/datei.md")
        self.assertEqual(result, data)

    def test_write_creates_parent_dirs(self):
        self.adapter.write("a/b/c/datei.txt", b"inhalt")
        full = os.path.join(self._tmpdir, "a", "b", "c", "datei.txt")
        self.assertTrue(os.path.isfile(full))

    def test_write_is_atomic_overwrite(self):
        self.adapter.write("datei.txt", b"alt")
        self.adapter.write("datei.txt", b"neu")
        self.assertEqual(self.adapter.read("datei.txt"), b"neu")

    def test_read_raises_storage_error_for_missing(self):
        from services.brand_voice_storage import StorageError
        with self.assertRaises(StorageError):
            self.adapter.read("gibts-nicht.txt")

    # ------------------------------------------------------------------
    # stat
    # ------------------------------------------------------------------

    def test_stat_returns_correct_size(self):
        data = b"12345"
        self.adapter.write("msg.bin", data)
        stat = self.adapter.stat("msg.bin")
        self.assertEqual(stat.size, len(data))

    def test_stat_mtime_is_utc_aware(self):
        self.adapter.write("ts.txt", b"x")
        stat = self.adapter.stat("ts.txt")
        self.assertIsNotNone(stat.mtime.tzinfo)
        self.assertEqual(stat.mtime.tzinfo, timezone.utc)

    def test_stat_etag_format(self):
        self.adapter.write("etag.txt", b"hallo")
        stat = self.adapter.stat("etag.txt")
        # Format: "<int_mtime>-<size>"
        parts = stat.etag.split("-")
        self.assertEqual(len(parts), 2)
        self.assertTrue(parts[0].isdigit(), f"Erwartet int, bekam: {parts[0]!r}")
        self.assertTrue(parts[1].isdigit(), f"Erwartet int, bekam: {parts[1]!r}")

    def test_stat_raises_storage_error_for_missing(self):
        from services.brand_voice_storage import StorageError
        with self.assertRaises(StorageError):
            self.adapter.stat("nicht-da.txt")

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    def test_list_empty_dir(self):
        eintraege = self.adapter.list("")
        self.assertEqual(eintraege, [])

    def test_list_returns_sorted_entries(self):
        self.adapter.write("z.txt", b"z")
        self.adapter.write("a.txt", b"a")
        self.adapter.write("m.txt", b"m")
        names = [e.name for e in self.adapter.list("")]
        self.assertEqual(names, sorted(names))

    def test_list_marks_directories(self):
        self.adapter.write("sub/datei.txt", b"x")
        eintraege = self.adapter.list("")
        verz = [e for e in eintraege if e.is_directory]
        self.assertEqual(len(verz), 1)
        self.assertEqual(verz[0].name, "sub")

    def test_list_entry_path_starts_with_slash(self):
        self.adapter.write("test.txt", b"x")
        eintraege = self.adapter.list("")
        for e in eintraege:
            self.assertTrue(e.path.startswith("/"), f"Pfad ohne '/': {e.path!r}")

    def test_list_raises_storage_error_for_missing_dir(self):
        from services.brand_voice_storage import StorageError
        with self.assertRaises(StorageError):
            self.adapter.list("nicht-vorhanden/")

    # ------------------------------------------------------------------
    # Path-Traversal-Abwehr
    # ------------------------------------------------------------------

    def test_path_traversal_blocked(self):
        from services.brand_voice_storage import StorageError
        with self.assertRaises(StorageError):
            self.adapter.read("../../etc/passwd")

    def test_path_traversal_blocked_encoded(self):
        from services.brand_voice_storage import StorageError
        with self.assertRaises(StorageError):
            self.adapter.read("../secret")

    def test_path_traversal_blocked_on_write(self):
        from services.brand_voice_storage import StorageError
        with self.assertRaises(StorageError):
            self.adapter.write("../evil.txt", b"hack")

    def test_path_traversal_blocked_on_stat(self):
        from services.brand_voice_storage import StorageError
        with self.assertRaises(StorageError):
            self.adapter.stat("../../etc/hosts")

    # ------------------------------------------------------------------
    # Integration: echte P01-Datei + _extract_section
    # ------------------------------------------------------------------

    def test_p01_real_file_sections_not_empty(self):
        """Laedt P01 aus content-truth/prompts/ und prueft System- und User-Prompt."""
        # Pfad relativ zum Backend-Verzeichnis (cwd beim Testlauf ist backend/)
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        content_truth = os.path.join(repo_root, "content-truth")

        from services.local_fs_storage import LocalFsStorageAdapter
        from services.prompt_loader import _extract_section

        adapter = LocalFsStorageAdapter(base_dir=content_truth)
        raw = adapter.read("prompts/P01-kundenkontext-extraktion.md")
        content = raw.decode("utf-8")

        system = _extract_section(content, "System-Prompt")
        user = _extract_section(content, "User-Prompt")

        self.assertTrue(len(system) > 0, "System-Prompt-Sektion ist leer")
        self.assertTrue(len(user) > 0, "User-Prompt-Sektion ist leer")


if __name__ == "__main__":
    unittest.main()
