"""
Tests fuer die Prompt-Studio-API (api/prompt_studio.py).

Strategie: Mini-FastAPI-App mit NUR dem prompt_studio-Router — kein main.py,
kein DB/Celery/Google-Import. Auth wird per dependency_overrides gefaket.

Fuer jeden Test-Lauf werden temporaere Base- und Overlay-Verzeichnisse
angelegt; get_studio_adapter() wird auf diese Verzeichnisse umgebogen.

Fuer pytest ist PYTHONPATH=backend und CONTENT_TRUTH_BASE_PATH gesetzt.
"""
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Modul-Direktlader (umgehen services/__init__.py)
# ---------------------------------------------------------------------------

def _load_module_from_file(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Stubs fuer Heavy-Packages (vor allen Modul-Ladern)
# ---------------------------------------------------------------------------
for _pkg in ("google", "google.generativeai", "anthropic"):
    if _pkg not in sys.modules:
        _m = types.ModuleType(_pkg)
        sys.modules[_pkg] = _m

# ---------------------------------------------------------------------------
# Fake Tenant-Klasse und get_tenant-Dependency-Override
# ---------------------------------------------------------------------------

class _FakeTenant:
    """Minimaler Tenant-Stub fuer den Auth-Override."""
    id = "00000000-0000-0000-0000-000000000001"
    enabled = True
    disabled_reason = None
    disabled_at = None


async def _fake_get_tenant():
    """Ersetzt get_tenant() in der Test-App — kein DB-Zugriff."""
    return _FakeTenant()


# ---------------------------------------------------------------------------
# dependencies.py-Stub (ersetzt echte Datei, die sqlalchemy/models braucht)
# ---------------------------------------------------------------------------
# Wir erstellen einen synthetischen dependencies-Stub der get_tenant exportiert,
# ohne die echte dependencies.py zu laden (diese wuerde sqlalchemy/models ziehen).

_deps_stub = types.ModuleType("dependencies")
_deps_stub.get_tenant = _fake_get_tenant
_deps_stub.get_db = MagicMock()
_deps_stub.get_tenant_id = MagicMock()
sys.modules["dependencies"] = _deps_stub

# ---------------------------------------------------------------------------
# Alle relevanten Service-Module direkt laden
# ---------------------------------------------------------------------------

_load_module_from_file("config", os.path.join(_BACKEND_DIR, "config.py"))
_load_module_from_file(
    "services.brand_voice_storage",
    os.path.join(_BACKEND_DIR, "services", "brand_voice_storage.py"),
)
_load_module_from_file(
    "services.local_fs_storage",
    os.path.join(_BACKEND_DIR, "services", "local_fs_storage.py"),
)
_load_module_from_file(
    "services.layered_storage",
    os.path.join(_BACKEND_DIR, "services", "layered_storage.py"),
)
_load_module_from_file(
    "services.prompt_loader",
    os.path.join(_BACKEND_DIR, "services", "prompt_loader.py"),
)
_load_module_from_file(
    "services.prompt_health_core",
    os.path.join(_BACKEND_DIR, "services", "prompt_health_core.py"),
)
_load_module_from_file(
    "api.prompt_studio",
    os.path.join(_BACKEND_DIR, "api", "prompt_studio.py"),
)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.prompt_studio as ps_module
from services.local_fs_storage import LocalFsStorageAdapter
from services.layered_storage import LayeredStorageAdapter

# ---------------------------------------------------------------------------
# Minimal-App fuer Tests (kein main.py-Lifespan/DB)
# ---------------------------------------------------------------------------

_app = FastAPI()
_app.include_router(ps_module.router, prefix="/api")
# Auth-Override: get_tenant wird durch _fake_get_tenant ersetzt
_app.dependency_overrides[_fake_get_tenant] = _fake_get_tenant

client = TestClient(_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Basis-Inhalte fuer Test-Fixtures
# ---------------------------------------------------------------------------

_GOOD_PROMPT = (
    "## System-Prompt\n"
    "Du bist ein hilfreicher Assistent.\n"
    "## User-Prompt\n"
    "Bitte hilf mir.\n"
)

_NO_SYSTEM_PROMPT = (
    "# Nur ein Titel\n"
    "Kein System-Prompt-Abschnitt hier.\n"
)

_GOOD_SCHEMA = json.dumps({
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"name": {"type": "string"}},
})

_BAD_JSON = "{ ungueltig json {{{ }"

_BAD_SCHEMA = json.dumps({
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": 123,  # type muss string sein
})


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_temp_dirs():
    """Erstellt temporaere base/overlay-Verzeichnisse und gibt sie zurueck."""
    tmpdir = tempfile.mkdtemp()
    base = os.path.join(tmpdir, "base")
    overlay = os.path.join(tmpdir, "overlay")
    os.makedirs(os.path.join(base, "prompts"), exist_ok=True)
    os.makedirs(os.path.join(base, "rules"), exist_ok=True)
    os.makedirs(os.path.join(base, "schemas"), exist_ok=True)
    os.makedirs(overlay, exist_ok=True)
    return tmpdir, base, overlay


def _write_file(directory, path, content):
    """Schreibt eine Datei in das Verzeichnis."""
    full = os.path.join(directory, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    encoding = None if isinstance(content, bytes) else "utf-8"
    with open(full, mode, encoding=encoding) as fh:
        fh.write(content)


def _patch_adapter(base_dir: str, overlay_dir: str):
    """Ueberschreibt get_studio_adapter() im Modul fuer einen Test."""
    def _factory():
        return LayeredStorageAdapter(
            overlay=LocalFsStorageAdapter(base_dir=overlay_dir),
            base=LocalFsStorageAdapter(base_dir=base_dir),
        )
    ps_module.get_studio_adapter = _factory


# ---------------------------------------------------------------------------
# Test-Klassen
# ---------------------------------------------------------------------------

class TestListFiles(unittest.TestCase):
    """GET /api/prompt-studio/files"""

    def setUp(self):
        self._tmpdir, self._base, self._overlay = _make_temp_dirs()
        _write_file(self._base, "prompts/P12-post-generierung.md", _GOOD_PROMPT)
        _write_file(self._base, "schemas/p01.schema.json", _GOOD_SCHEMA)
        _patch_adapter(self._base, self._overlay)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_list_returns_200(self):
        resp = client.get("/api/prompt-studio/files")
        self.assertEqual(resp.status_code, 200)

    def test_list_contains_files(self):
        resp = client.get("/api/prompt-studio/files")
        data = resp.json()
        paths = [f["path"] for f in data["files"]]
        self.assertIn("prompts/P12-post-generierung.md", paths)
        self.assertIn("schemas/p01.schema.json", paths)

    def test_list_source_is_base_without_overlay(self):
        resp = client.get("/api/prompt-studio/files")
        data = resp.json()
        entry = next(
            f for f in data["files"] if f["path"] == "prompts/P12-post-generierung.md"
        )
        self.assertEqual(entry["source"], "base")
        self.assertFalse(entry["has_overlay"])

    def test_list_overlay_marked_correctly(self):
        """Datei im Overlay erscheint mit source='overlay' und has_overlay=True."""
        _write_file(self._overlay, "prompts/P12-post-generierung.md", "## System-Prompt\nOverlay\n")
        resp = client.get("/api/prompt-studio/files")
        data = resp.json()
        entry = next(
            f for f in data["files"] if f["path"] == "prompts/P12-post-generierung.md"
        )
        self.assertEqual(entry["source"], "overlay")
        self.assertTrue(entry["has_overlay"])

    def test_list_base_mtime_is_set(self):
        resp = client.get("/api/prompt-studio/files")
        data = resp.json()
        entry = next(
            f for f in data["files"] if f["path"] == "prompts/P12-post-generierung.md"
        )
        self.assertIsNotNone(entry["base_mtime"])


class TestGetFile(unittest.TestCase):
    """GET /api/prompt-studio/files/{path}"""

    def setUp(self):
        self._tmpdir, self._base, self._overlay = _make_temp_dirs()
        _write_file(self._base, "prompts/P12-post-generierung.md", _GOOD_PROMPT)
        _write_file(self._base, "schemas/p01.schema.json", _GOOD_SCHEMA)
        _patch_adapter(self._base, self._overlay)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_get_returns_200(self):
        resp = client.get("/api/prompt-studio/files/prompts/P12-post-generierung.md")
        self.assertEqual(resp.status_code, 200)

    def test_get_returns_content(self):
        resp = client.get("/api/prompt-studio/files/prompts/P12-post-generierung.md")
        data = resp.json()
        self.assertIn("System-Prompt", data["content"])

    def test_get_returns_sha256(self):
        resp = client.get("/api/prompt-studio/files/prompts/P12-post-generierung.md")
        data = resp.json()
        import hashlib
        expected = hashlib.sha256(_GOOD_PROMPT.encode("utf-8")).hexdigest()
        self.assertEqual(data["sha256"], expected)

    def test_get_extracts_system_prompt(self):
        resp = client.get("/api/prompt-studio/files/prompts/P12-post-generierung.md")
        data = resp.json()
        self.assertIn("hilfreicher Assistent", data["system_prompt"])

    def test_get_extracts_user_prompt(self):
        resp = client.get("/api/prompt-studio/files/prompts/P12-post-generierung.md")
        data = resp.json()
        self.assertIn("Bitte hilf mir", data["user_prompt"])

    def test_get_health_for_md(self):
        resp = client.get("/api/prompt-studio/files/prompts/P12-post-generierung.md")
        data = resp.json()
        self.assertIsNotNone(data["health"])
        self.assertIn(data["health"]["status"], ("ok", "weird"))

    def test_get_no_health_for_json(self):
        resp = client.get("/api/prompt-studio/files/schemas/p01.schema.json")
        data = resp.json()
        self.assertIsNone(data["health"])

    def test_get_404_for_missing(self):
        resp = client.get("/api/prompt-studio/files/prompts/gibts-nicht.md")
        self.assertEqual(resp.status_code, 404)

    def test_get_400_for_traversal(self):
        resp = client.get("/api/prompt-studio/files/prompts/../config.py")
        self.assertEqual(resp.status_code, 400)

    def test_get_400_for_disallowed_path(self):
        resp = client.get("/api/prompt-studio/files/etc/passwd")
        self.assertEqual(resp.status_code, 400)

    def test_get_400_for_txt_extension(self):
        resp = client.get("/api/prompt-studio/files/prompts/x.txt")
        self.assertEqual(resp.status_code, 400)


class TestValidate(unittest.TestCase):
    """POST /api/prompt-studio/files/{path}/validate"""

    def setUp(self):
        self._tmpdir, self._base, self._overlay = _make_temp_dirs()
        _write_file(self._base, "prompts/P12-post-generierung.md", _GOOD_PROMPT)
        _write_file(self._base, "schemas/p01.schema.json", _GOOD_SCHEMA)
        _patch_adapter(self._base, self._overlay)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_validate_good_md_returns_ok(self):
        resp = client.post(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md/validate",
            json={"content": _GOOD_PROMPT},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["health"]["status"], "ok")

    def test_validate_md_without_system_returns_weird(self):
        resp = client.post(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md/validate",
            json={"content": _NO_SYSTEM_PROMPT},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["valid"])
        self.assertIn("SYSTEM_PROMPT_LEER", data["health"]["issues"])

    def test_validate_good_schema_returns_ok(self):
        resp = client.post(
            "/api/prompt-studio/files/schemas/p01.schema.json/validate",
            json={"content": _GOOD_SCHEMA},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["schema_errors"], [])

    def test_validate_bad_json_returns_invalid(self):
        resp = client.post(
            "/api/prompt-studio/files/schemas/p01.schema.json/validate",
            json={"content": _BAD_JSON},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["valid"])
        self.assertTrue(len(data["schema_errors"]) > 0)

    def test_validate_bad_schema_type_returns_invalid(self):
        resp = client.post(
            "/api/prompt-studio/files/schemas/p01.schema.json/validate",
            json={"content": _BAD_SCHEMA},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["valid"])
        self.assertTrue(len(data["schema_errors"]) > 0)

    def test_validate_413_for_oversized_content(self):
        big = "x" * (512_001)
        resp = client.post(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md/validate",
            json={"content": big},
        )
        self.assertEqual(resp.status_code, 413)


class TestSave(unittest.TestCase):
    """PUT /api/prompt-studio/files/{path}"""

    def setUp(self):
        self._tmpdir, self._base, self._overlay = _make_temp_dirs()
        _write_file(self._base, "prompts/P12-post-generierung.md", _GOOD_PROMPT)
        _write_file(self._base, "schemas/p01.schema.json", _GOOD_SCHEMA)
        _patch_adapter(self._base, self._overlay)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _sha256(self, content: str) -> str:
        import hashlib
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def test_save_creates_overlay_file(self):
        new_content = _GOOD_PROMPT + "\n<!-- geaendert -->"
        resp = client.put(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md",
            json={"content": new_content},
        )
        self.assertEqual(resp.status_code, 200)
        # Overlay-Datei physisch pruefen
        overlay_file = os.path.join(
            self._overlay, "prompts", "P12-post-generierung.md"
        )
        self.assertTrue(os.path.isfile(overlay_file))
        with open(overlay_file, "r", encoding="utf-8") as fh:
            self.assertIn("geaendert", fh.read())

    def test_save_response_source_is_overlay(self):
        resp = client.put(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md",
            json={"content": _GOOD_PROMPT},
        )
        data = resp.json()
        self.assertEqual(data["source"], "overlay")

    def test_save_response_contains_sha256(self):
        resp = client.put(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md",
            json={"content": _GOOD_PROMPT},
        )
        data = resp.json()
        expected_sha = self._sha256(_GOOD_PROMPT)
        self.assertEqual(data["sha256"], expected_sha)

    def test_save_response_contains_validation(self):
        resp = client.put(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md",
            json={"content": _GOOD_PROMPT},
        )
        data = resp.json()
        self.assertIn("validation", data)
        self.assertIn("valid", data["validation"])

    def test_save_409_on_sha_conflict(self):
        """base_sha256 stimmt nicht ueberein → 409."""
        resp = client.put(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md",
            json={"content": _GOOD_PROMPT, "base_sha256": "0" * 64},
        )
        self.assertEqual(resp.status_code, 409)

    def test_save_200_with_correct_sha(self):
        """base_sha256 korrekt → 200."""
        correct_sha = self._sha256(_GOOD_PROMPT)
        resp = client.put(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md",
            json={"content": _GOOD_PROMPT, "base_sha256": correct_sha},
        )
        self.assertEqual(resp.status_code, 200)

    def test_save_422_for_broken_schema_json(self):
        """Kaputtes Schema-JSON → 422 (harter Block)."""
        resp = client.put(
            "/api/prompt-studio/files/schemas/p01.schema.json",
            json={"content": _BAD_JSON},
        )
        self.assertEqual(resp.status_code, 422)

    def test_save_422_for_invalid_schema_type(self):
        """Schema mit type=123 → 422."""
        resp = client.put(
            "/api/prompt-studio/files/schemas/p01.schema.json",
            json={"content": _BAD_SCHEMA},
        )
        self.assertEqual(resp.status_code, 422)

    def test_save_404_for_file_not_in_base(self):
        """Neue Datei ohne Base-Pendant → 404 (kein Anlegen in v1)."""
        resp = client.put(
            "/api/prompt-studio/files/prompts/neue-datei.md",
            json={"content": _GOOD_PROMPT},
        )
        self.assertEqual(resp.status_code, 404)

    def test_save_413_for_oversized(self):
        big = "x" * (512_001)
        resp = client.put(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md",
            json={"content": big},
        )
        self.assertEqual(resp.status_code, 413)

    def test_save_md_with_weird_health_is_allowed(self):
        """Prompt mit SYSTEM_PROMPT_LEER → Save ist erlaubt (Warnung, kein Block)."""
        resp = client.put(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md",
            json={"content": _NO_SYSTEM_PROMPT},
        )
        # 200 — gespeichert, aber Validation-Status ist "weird"
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["validation"]["valid"])


class TestRevert(unittest.TestCase):
    """DELETE /api/prompt-studio/files/{path}/overlay"""

    def setUp(self):
        self._tmpdir, self._base, self._overlay = _make_temp_dirs()
        _write_file(self._base, "prompts/P12-post-generierung.md", _GOOD_PROMPT)
        _patch_adapter(self._base, self._overlay)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_revert_removes_overlay(self):
        # Erst speichern
        client.put(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md",
            json={"content": _GOOD_PROMPT + "\n<!-- overlay -->"},
        )
        overlay_file = os.path.join(
            self._overlay, "prompts", "P12-post-generierung.md"
        )
        self.assertTrue(os.path.isfile(overlay_file))

        # Revert
        resp = client.delete(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md/overlay"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["reverted"])
        self.assertFalse(os.path.exists(overlay_file))

    def test_revert_get_returns_base_content(self):
        """Nach Revert liefert GET wieder den Base-Inhalt."""
        # Overlay anlegen
        client.put(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md",
            json={"content": "## System-Prompt\nOverlay\n"},
        )
        # Revert
        client.delete(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md/overlay"
        )
        # GET muss Base-Inhalt zeigen
        resp = client.get(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md"
        )
        data = resp.json()
        self.assertIn("hilfreicher Assistent", data["content"])
        self.assertEqual(data["source"], "base")

    def test_revert_idempotent(self):
        """Zweiter Revert-Aufruf → reverted=false, trotzdem 200."""
        resp = client.delete(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md/overlay"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["reverted"])

    def test_revert_response_source_is_base(self):
        resp = client.delete(
            "/api/prompt-studio/files/prompts/P12-post-generierung.md/overlay"
        )
        data = resp.json()
        self.assertEqual(data["source"], "base")


class TestAuth(unittest.TestCase):
    """Auth-Smoke-Tests: Auth-Dependency wird durch eine verwerfende Funktion ersetzt."""

    def test_unauthorized_returns_401(self):
        """Auth-Dependency wirft 401 → alle Endpunkte verweigert."""
        from fastapi import HTTPException as _HTTPException

        async def _reject_all():
            raise _HTTPException(status_code=401, detail="Invalid API key")

        app_secured = FastAPI()
        app_secured.include_router(ps_module.router, prefix="/api")
        # Auth-Override: ersetzt fake_get_tenant durch verwerfende Funktion
        app_secured.dependency_overrides[_fake_get_tenant] = _reject_all
        client_secured = TestClient(app_secured, raise_server_exceptions=False)

        resp = client_secured.get("/api/prompt-studio/files")
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
