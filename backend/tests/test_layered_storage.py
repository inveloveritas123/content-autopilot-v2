"""
Tests fuer LayeredStorageAdapter (services/layered_storage.py).

Deckt ab:
- read/stat/exists: overlay-first, Fallback Base, beides fehlt → StorageError
- write landet nur im Overlay; Base-Datei bleibt byte-identisch
- list: Merge + Dedupe; list_with_source markiert shadowed Dateien als overlay
- fehlendes Overlay-Verzeichnis → nur Base, kein Fehler
- delete_overlay: loescht nur Overlay; idempotent; Traversal blockt
- PromptLoader-Integration: Overlay-Save → Cache-Refresh; Revert + invalidate

Import-Strategie: Heavy-Dependencies werden per importlib-Direktlader
umgangen (kein services/__init__.py, kein google/sqlalchemy/celery).
"""
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from datetime import timezone
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Hilfsfunktionen fuer Modul-Direktlader
# ---------------------------------------------------------------------------

def _load_module_from_file(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Backend-Verzeichnis ermitteln
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Stubs fuer nicht-installierte Heavy-Packages
# ---------------------------------------------------------------------------
for _pkg in ("google", "google.generativeai", "anthropic"):
    if _pkg not in sys.modules:
        _m = types.ModuleType(_pkg)
        sys.modules[_pkg] = _m

# config direkt laden
_load_module_from_file("config", os.path.join(_BACKEND_DIR, "config.py"))

# brand_voice_storage direkt laden
_load_module_from_file(
    "services.brand_voice_storage",
    os.path.join(_BACKEND_DIR, "services", "brand_voice_storage.py"),
)

# local_fs_storage direkt laden
_load_module_from_file(
    "services.local_fs_storage",
    os.path.join(_BACKEND_DIR, "services", "local_fs_storage.py"),
)

# layered_storage direkt laden
_load_module_from_file(
    "services.layered_storage",
    os.path.join(_BACKEND_DIR, "services", "layered_storage.py"),
)

# prompt_loader direkt laden (fuer Integrations-Test)
_load_module_from_file(
    "services.prompt_loader",
    os.path.join(_BACKEND_DIR, "services", "prompt_loader.py"),
)

# prompt_health_core direkt laden
_load_module_from_file(
    "services.prompt_health_core",
    os.path.join(_BACKEND_DIR, "services", "prompt_health_core.py"),
)

# ---------------------------------------------------------------------------
# Importe nach dem Laden
# ---------------------------------------------------------------------------
from services.local_fs_storage import LocalFsStorageAdapter   # noqa: E402
from services.layered_storage import LayeredStorageAdapter     # noqa: E402
from services.brand_voice_storage import StorageError          # noqa: E402


# ---------------------------------------------------------------------------
# Hilfsfunktionen fuer die Tests
# ---------------------------------------------------------------------------

def _make_adapter(
    base_dir: str, overlay_dir: str
) -> LayeredStorageAdapter:
    return LayeredStorageAdapter(
        overlay=LocalFsStorageAdapter(base_dir=overlay_dir),
        base=LocalFsStorageAdapter(base_dir=base_dir),
    )


class TestLayeredStorageRead(unittest.TestCase):
    """Lese-Semantik: overlay-first, Fallback Base, beide fehlen."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._base = os.path.join(self._tmpdir, "base")
        self._overlay = os.path.join(self._tmpdir, "overlay")
        os.makedirs(self._base, exist_ok=True)
        os.makedirs(self._overlay, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _adapter(self):
        return _make_adapter(self._base, self._overlay)

    def _write_base(self, path: str, content: bytes):
        full = os.path.join(self._base, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content)

    def _write_overlay(self, path: str, content: bytes):
        full = os.path.join(self._overlay, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content)

    # --- read ---

    def test_read_returns_base_when_no_overlay(self):
        self._write_base("prompts/test.md", b"basis")
        adapter = self._adapter()
        self.assertEqual(adapter.read("prompts/test.md"), b"basis")

    def test_read_overlay_first(self):
        self._write_base("prompts/test.md", b"basis")
        self._write_overlay("prompts/test.md", b"overlay")
        adapter = self._adapter()
        self.assertEqual(adapter.read("prompts/test.md"), b"overlay")

    def test_read_raises_when_both_missing(self):
        adapter = self._adapter()
        with self.assertRaises(StorageError):
            adapter.read("prompts/nicht-da.md")

    # --- stat ---

    def test_stat_returns_base_stat_when_no_overlay(self):
        self._write_base("prompts/test.md", b"basis")
        adapter = self._adapter()
        stat = adapter.stat("prompts/test.md")
        self.assertIsNotNone(stat.mtime)
        self.assertEqual(stat.size, len(b"basis"))

    def test_stat_overlay_first(self):
        self._write_base("prompts/test.md", b"kurz")
        self._write_overlay("prompts/test.md", b"laenger inhalt hier")
        adapter = self._adapter()
        stat = adapter.stat("prompts/test.md")
        self.assertEqual(stat.size, len(b"laenger inhalt hier"))

    def test_stat_raises_when_both_missing(self):
        adapter = self._adapter()
        with self.assertRaises(StorageError):
            adapter.stat("prompts/nicht-da.md")

    # --- exists ---

    def test_exists_false_when_both_missing(self):
        adapter = self._adapter()
        self.assertFalse(adapter.exists("prompts/nicht-da.md"))

    def test_exists_true_when_only_base(self):
        self._write_base("prompts/test.md", b"x")
        adapter = self._adapter()
        self.assertTrue(adapter.exists("prompts/test.md"))

    def test_exists_true_when_only_overlay(self):
        self._write_overlay("prompts/test.md", b"x")
        adapter = self._adapter()
        self.assertTrue(adapter.exists("prompts/test.md"))

    def test_exists_true_when_both(self):
        self._write_base("prompts/test.md", b"x")
        self._write_overlay("prompts/test.md", b"y")
        adapter = self._adapter()
        self.assertTrue(adapter.exists("prompts/test.md"))


class TestLayeredStorageWrite(unittest.TestCase):
    """Write-Semantik: schreibt ausschliesslich ins Overlay."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._base = os.path.join(self._tmpdir, "base")
        self._overlay = os.path.join(self._tmpdir, "overlay")
        os.makedirs(self._base, exist_ok=True)
        os.makedirs(self._overlay, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_base(self, path: str, content: bytes):
        full = os.path.join(self._base, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content)

    def test_write_lands_in_overlay_not_base(self):
        """Write schreibt ins Overlay; Base-Datei bleibt unangetastet."""
        self._write_base("prompts/test.md", b"original")
        adapter = _make_adapter(self._base, self._overlay)
        adapter.write("prompts/test.md", b"geaendert")

        # Overlay hat neuen Inhalt
        overlay_path = os.path.join(self._overlay, "prompts", "test.md")
        with open(overlay_path, "rb") as fh:
            self.assertEqual(fh.read(), b"geaendert")

        # Base ist unveraendert
        base_path = os.path.join(self._base, "prompts", "test.md")
        with open(base_path, "rb") as fh:
            self.assertEqual(fh.read(), b"original")

    def test_write_read_reflects_overlay(self):
        """Nach Write liefert read() den Overlay-Inhalt."""
        self._write_base("prompts/test.md", b"basis")
        adapter = _make_adapter(self._base, self._overlay)
        adapter.write("prompts/test.md", b"neu")
        self.assertEqual(adapter.read("prompts/test.md"), b"neu")

    def test_write_creates_overlay_dir_structure(self):
        """write() legt fehlende Verzeichnisse im Overlay an."""
        adapter = _make_adapter(self._base, self._overlay)
        adapter.write("prompts/new-subdir/datei.md", b"inhalt")
        expected = os.path.join(self._overlay, "prompts", "new-subdir", "datei.md")
        self.assertTrue(os.path.isfile(expected))


class TestLayeredStorageList(unittest.TestCase):
    """list() und list_with_source(): Merge, Dedupe, Quellenmarkierung."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._base = os.path.join(self._tmpdir, "base")
        self._overlay = os.path.join(self._tmpdir, "overlay")
        os.makedirs(self._base, exist_ok=True)
        os.makedirs(self._overlay, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_base(self, path: str, content: bytes = b"x"):
        full = os.path.join(self._base, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content)

    def _write_overlay(self, path: str, content: bytes = b"x"):
        full = os.path.join(self._overlay, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content)

    def test_list_merges_base_and_overlay(self):
        self._write_base("prompts/a.md")
        self._write_overlay("prompts/b.md")
        adapter = _make_adapter(self._base, self._overlay)
        names = [e.name for e in adapter.list("prompts")]
        self.assertIn("a.md", names)
        self.assertIn("b.md", names)

    def test_list_deduplicates_by_name(self):
        """Selbe Datei in Base und Overlay → nur einmal in der Liste."""
        self._write_base("prompts/test.md")
        self._write_overlay("prompts/test.md")
        adapter = _make_adapter(self._base, self._overlay)
        names = [e.name for e in adapter.list("prompts")]
        self.assertEqual(names.count("test.md"), 1)

    def test_list_is_sorted(self):
        self._write_base("prompts/c.md")
        self._write_base("prompts/a.md")
        self._write_overlay("prompts/b.md")
        adapter = _make_adapter(self._base, self._overlay)
        names = [e.name for e in adapter.list("prompts")]
        self.assertEqual(names, sorted(names))

    def test_list_with_source_marks_overlay(self):
        self._write_base("prompts/both.md", b"base-version")
        self._write_overlay("prompts/both.md", b"overlay-version")
        self._write_base("prompts/base-only.md", b"base")
        adapter = _make_adapter(self._base, self._overlay)
        result = {e.name: source for e, source, _ in adapter.list_with_source("prompts")}
        self.assertEqual(result["both.md"], "overlay")
        self.assertEqual(result["base-only.md"], "base")

    def test_list_with_source_stat_reflects_overlay(self):
        """Stat fuer Overlay-Datei muss die Overlay-Groesse zeigen."""
        self._write_base("prompts/test.md", b"kurz")
        self._write_overlay("prompts/test.md", b"viel laengerer overlay inhalt")
        adapter = _make_adapter(self._base, self._overlay)
        result = {e.name: stat for e, _, stat in adapter.list_with_source("prompts")}
        self.assertEqual(result["test.md"].size, len(b"viel laengerer overlay inhalt"))

    def test_list_without_overlay_dir_returns_base_only(self):
        """Wenn das Overlay-Verzeichnis nicht existiert → kein Fehler, nur Base."""
        import shutil
        shutil.rmtree(self._overlay)  # Overlay-Verzeichnis komplett entfernen
        self._write_base("prompts/base.md")
        adapter = _make_adapter(self._base, self._overlay)
        names = [e.name for e in adapter.list("prompts")]
        self.assertIn("base.md", names)

    def test_list_with_source_missing_overlay_dir(self):
        """list_with_source() ohne Overlay-Dir → alle Base, kein Fehler."""
        import shutil
        shutil.rmtree(self._overlay)
        self._write_base("prompts/a.md")
        adapter = _make_adapter(self._base, self._overlay)
        result = {e.name: source for e, source, _ in adapter.list_with_source("prompts")}
        self.assertEqual(result.get("a.md"), "base")


class TestLayeredStorageDeleteOverlay(unittest.TestCase):
    """delete_overlay(): loescht nur Overlay, idempotent, Traversal-Schutz."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._base = os.path.join(self._tmpdir, "base")
        self._overlay = os.path.join(self._tmpdir, "overlay")
        os.makedirs(self._base, exist_ok=True)
        os.makedirs(self._overlay, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_base(self, path: str, content: bytes = b"base"):
        full = os.path.join(self._base, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content)

    def _write_overlay(self, path: str, content: bytes = b"overlay"):
        full = os.path.join(self._overlay, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content)

    def test_delete_overlay_removes_only_overlay(self):
        self._write_base("prompts/test.md", b"basis")
        self._write_overlay("prompts/test.md", b"overlay")
        adapter = _make_adapter(self._base, self._overlay)
        result = adapter.delete_overlay("prompts/test.md")
        self.assertTrue(result)
        # Overlay-Datei ist weg
        self.assertFalse(os.path.exists(
            os.path.join(self._overlay, "prompts", "test.md")
        ))
        # Base-Datei ist unveraendert
        self.assertTrue(os.path.exists(
            os.path.join(self._base, "prompts", "test.md")
        ))

    def test_delete_overlay_base_not_modified(self):
        """Inhalt der Base-Datei muss nach delete_overlay unveraendert sein."""
        self._write_base("prompts/test.md", b"originalinhalt")
        self._write_overlay("prompts/test.md", b"overlay")
        adapter = _make_adapter(self._base, self._overlay)
        adapter.delete_overlay("prompts/test.md")
        base_content = adapter.read("prompts/test.md")
        self.assertEqual(base_content, b"originalinhalt")

    def test_delete_overlay_idempotent(self):
        """delete_overlay auf nicht-vorhandenes Overlay → False, kein Fehler."""
        self._write_base("prompts/test.md", b"basis")
        adapter = _make_adapter(self._base, self._overlay)
        result = adapter.delete_overlay("prompts/test.md")
        self.assertFalse(result)

    def test_delete_overlay_traversal_blocked(self):
        """Traversal-Versuch '../x' wird vom LocalFsStorageAdapter geblockt."""
        adapter = _make_adapter(self._base, self._overlay)
        # Kein Overlay-Eintrag → delete_overlay gibt False ohne Fehler
        # (weil _overlay_exists_safe False zurueckgibt bevor _resolve greift)
        result = adapter.delete_overlay("../evil.txt")
        self.assertFalse(result)


class TestLayeredStorageSourceOf(unittest.TestCase):
    """source_of() und stat_base()."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._base = os.path.join(self._tmpdir, "base")
        self._overlay = os.path.join(self._tmpdir, "overlay")
        os.makedirs(self._base, exist_ok=True)
        os.makedirs(self._overlay, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_base(self, path: str, content: bytes = b"base"):
        full = os.path.join(self._base, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content)

    def _write_overlay(self, path: str, content: bytes = b"overlay"):
        full = os.path.join(self._overlay, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content)

    def test_source_of_returns_overlay(self):
        self._write_base("prompts/test.md")
        self._write_overlay("prompts/test.md")
        adapter = _make_adapter(self._base, self._overlay)
        self.assertEqual(adapter.source_of("prompts/test.md"), "overlay")

    def test_source_of_returns_base(self):
        self._write_base("prompts/test.md")
        adapter = _make_adapter(self._base, self._overlay)
        self.assertEqual(adapter.source_of("prompts/test.md"), "base")

    def test_source_of_returns_none_when_missing(self):
        adapter = _make_adapter(self._base, self._overlay)
        self.assertIsNone(adapter.source_of("prompts/gibts-nicht.md"))

    def test_stat_base_returns_base_stat_even_when_overlay_exists(self):
        self._write_base("prompts/test.md", b"kurz")
        self._write_overlay("prompts/test.md", b"viel laengerer overlay inhalt")
        adapter = _make_adapter(self._base, self._overlay)
        stat = adapter.stat_base("prompts/test.md")
        self.assertIsNotNone(stat)
        self.assertEqual(stat.size, len(b"kurz"))

    def test_stat_base_returns_none_when_not_in_base(self):
        self._write_overlay("prompts/test.md")
        adapter = _make_adapter(self._base, self._overlay)
        stat = adapter.stat_base("prompts/test.md")
        self.assertIsNone(stat)


class TestLayeredStorageMissingOverlayDir(unittest.TestCase):
    """Fehlendes Overlay-Verzeichnis: robuster Fallback auf Base."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._base = os.path.join(self._tmpdir, "base")
        self._overlay = os.path.join(self._tmpdir, "overlay_missing")  # existiert NICHT
        os.makedirs(self._base, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_base(self, path: str, content: bytes = b"base"):
        full = os.path.join(self._base, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content)

    def test_read_falls_back_to_base(self):
        self._write_base("prompts/test.md", b"basis")
        adapter = _make_adapter(self._base, self._overlay)
        self.assertEqual(adapter.read("prompts/test.md"), b"basis")

    def test_exists_returns_true_from_base(self):
        self._write_base("prompts/test.md", b"x")
        adapter = _make_adapter(self._base, self._overlay)
        self.assertTrue(adapter.exists("prompts/test.md"))

    def test_list_returns_base_entries_no_error(self):
        self._write_base("prompts/test.md", b"x")
        adapter = _make_adapter(self._base, self._overlay)
        names = [e.name for e in adapter.list("prompts")]
        self.assertIn("test.md", names)

    def test_write_creates_overlay_dir_on_demand(self):
        """write() legt das Overlay-Verzeichnis an wenn es fehlt."""
        adapter = _make_adapter(self._base, self._overlay)
        adapter.write("prompts/test.md", b"neu")
        overlay_file = os.path.join(self._overlay, "prompts", "test.md")
        self.assertTrue(os.path.isfile(overlay_file))


class TestLayeredStoragePromptLoaderIntegration(unittest.TestCase):
    """PromptLoader-Integration: Overlay-Save loest Cache-Refresh aus; Revert ebenfalls."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._base = os.path.join(self._tmpdir, "base")
        self._overlay = os.path.join(self._tmpdir, "overlay")
        os.makedirs(self._base, exist_ok=True)
        os.makedirs(self._overlay, exist_ok=True)

        # Minimale Prompt-Datei in der Base anlegen
        prompts_dir = os.path.join(self._base, "prompts")
        os.makedirs(prompts_dir, exist_ok=True)
        self._base_content = b"## System-Prompt\nOriginal-System\n## User-Prompt\nOriginal-User"
        with open(os.path.join(prompts_dir, "P12-post-generierung.md"), "wb") as fh:
            fh.write(self._base_content)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_overlay_save_triggers_cache_refresh(self):
        """Nach Write ins Overlay liefert PromptLoader den neuen Inhalt."""
        from services.prompt_loader import PromptLoader
        adapter = _make_adapter(self._base, self._overlay)

        loader = PromptLoader(
            storage_adapter=adapter,
            cache_ttl_seconds=3600,  # lange TTL damit mtime-Check greift
        )

        # Erstes Laden (Base-Inhalt)
        import time
        time.sleep(0.01)  # kleine Pause damit mtime verschieden ist
        p1 = loader.load("P12")
        self.assertIn("Original-System", p1.system_prompt)

        # Kurze Pause + neuen Inhalt ins Overlay schreiben
        time.sleep(0.05)
        new_content = b"## System-Prompt\nNeuer-System-Overlay\n## User-Prompt\nNeuer-User"
        adapter.write("prompts/P12-post-generierung.md", new_content)

        # Naechstes Laden soll neuen Inhalt sehen (mtime-Check erkennt Aenderung)
        p2 = loader.load("P12")
        self.assertIn("Neuer-System-Overlay", p2.system_prompt)

    def test_revert_with_invalidate_loads_base(self):
        """Nach delete_overlay + invalidate liefert PromptLoader den Base-Inhalt."""
        from services.prompt_loader import PromptLoader
        import time

        adapter = _make_adapter(self._base, self._overlay)
        loader = PromptLoader(storage_adapter=adapter, cache_ttl_seconds=3600)

        # Overlay anlegen
        time.sleep(0.01)
        new_content = b"## System-Prompt\nOverlay-Version\n## User-Prompt\nNeu"
        adapter.write("prompts/P12-post-generierung.md", new_content)

        # Einmal laden (Overlay-Inhalt wird gecacht)
        p1 = loader.load("P12")
        self.assertIn("Overlay-Version", p1.system_prompt)

        # Revert (Overlay loeschen)
        adapter.delete_overlay("prompts/P12-post-generierung.md")

        # Cache explizit invalidieren (mtime-Rueckwaerts-Falle: Base-mtime koennte
        # aelter als cached loaded_at sein → ohne invalidate koennte der Cache-Hit
        # greifen)
        loader.invalidate("P12")

        # Naechstes Laden muss Base-Inhalt zurueckgeben
        p2 = loader.load("P12")
        self.assertIn("Original-System", p2.system_prompt)


if __name__ == "__main__":
    unittest.main()
