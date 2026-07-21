"""Tests für Admin Session-Auth + API-Key-Verwaltung (Issue #98)

Ausführung (lokal):
    cd backend && PYTHONPATH=. \
      /pfad/zu/.venv/bin/python -m pytest tests/test_admin_auth.py -q

Strategie: alle schweren Deps (sqlalchemy, config, models, services.llm,
dependencies) werden via sys.modules-Stubs vor dem ersten Import von
api.admin_auth injiziert. Damit läuft die Suite auf dem lokalen Py3.9-venv
ohne installiertes sqlalchemy/sqlalchemy.ext.asyncio.

In CI (Docker, Py3.11+, vollständige requirements.txt) laufen alle Tests
echte Imports — Stubs werden NICHT injiziert, wenn Module bereits geladen.

Reihenfolge-Härtung (2026-07-21): tests/conftest.py::pytest_collectstart setzt
`dependencies`, `models.base`, `models.tenant` vor JEDER Testdatei-Collection auf
ihren echten (Baseline-)Zustand zurück (siehe conftest.py-Docstring). Die früheren
`if "X" not in sys.modules`-Guards dieser Datei gingen implizit davon aus, dass ein
einmal gesetzter Stub bis zur Testausführung bestehen bleibt — das gilt nicht mehr
zuverlässig, weil das Modul zwischen Collection und Ausführung anderer Dateien mal
vorhanden, mal (durch den Hook) zurückgesetzt sein kann. Fix: deterministische
Helfer `_ensure_package` / `_ensure_attr` (Vorbild: test_telegram_outbound_pertenant.py)
stellen die benötigten Stub-Attribute IMMER additiv sicher, unabhängig vom Vorzustand.
"""

from __future__ import annotations

import sys
import types


def _ensure_stub(name: str) -> types.ModuleType:
    """Legt sys.modules[name] als leeres ModuleType an, falls es fehlt (idempotent)."""
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
    return sys.modules[name]


def _ensure_package(name: str) -> types.ModuleType:
    """Wie _ensure_stub, garantiert aber zusätzlich ein gültiges __path__.

    Macht aus einem bloßen ModuleType ein echtes Package (importierbare
    Submodule wie models.base). Robust gegen einen kaputten Nicht-Package-Stub
    aus einer anderen Testdatei: __path__ wird auch dann nachgerüstet, wenn das
    Modul bereits in sys.modules steht.
    """
    mod = _ensure_stub(name)
    if not hasattr(mod, "__path__"):
        mod.__path__ = []
    return mod


def _ensure_attr(module: types.ModuleType, attr: str, factory) -> None:
    """Setzt `attr` auf `module` nur, wenn es dort noch fehlt (additiv).

    Ein bereits real geladenes Modul (echte SQLAlchemy-Factories/Klassen) wird
    NICHT überschrieben. Ein (teilweise) kaputter/zurückgesetzter Stub bekommt
    das fehlende Attribut deterministisch nachgerüstet.
    """
    if not hasattr(module, attr):
        setattr(module, attr, factory())


def _maybe_stub(name: str, factory):
    """Setzt sys.modules[name] nur wenn noch nicht vorhanden."""
    if name not in sys.modules:
        sys.modules[name] = factory()


# --- sqlalchemy (real if installed, stub only as fallback) ---
# NOTE: stub is needed so mock-DB patterns (str(query).upper()) work;
# real TextClause also supports str() so either way is fine.
try:
    import sqlalchemy
    import sqlalchemy.dialects.postgresql
    import sqlalchemy.ext.asyncio
    import sqlalchemy.orm
    import sqlalchemy.orm.attributes  # noqa: F401
except ImportError:

    def _make_sqlalchemy_stub():
        sa = types.ModuleType("sqlalchemy")
        sa.text = lambda q: q
        sa.select = lambda *a, **kw: None
        sa.Boolean = None
        sa.DateTime = None
        sa.String = lambda *a, **kw: None
        sa.Text = None
        sa.func = types.SimpleNamespace(now=lambda: None)
        return sa

    if "sqlalchemy" not in sys.modules:
        sys.modules["sqlalchemy"] = _make_sqlalchemy_stub()
    if "sqlalchemy.ext" not in sys.modules:
        sys.modules["sqlalchemy.ext"] = types.ModuleType("sqlalchemy.ext")
    if "sqlalchemy.ext.asyncio" not in sys.modules:
        _sa_async = types.ModuleType("sqlalchemy.ext.asyncio")
        _sa_async.AsyncSession = object
        _sa_async.create_async_engine = lambda *a, **kw: None
        sys.modules["sqlalchemy.ext.asyncio"] = _sa_async
    if "sqlalchemy.orm" not in sys.modules:
        _sa_orm = types.ModuleType("sqlalchemy.orm")
        _sa_orm.Mapped = object
        _sa_orm.mapped_column = lambda *a, **kw: None
        _sa_orm.relationship = lambda *a, **kw: None
        _sa_orm.sessionmaker = lambda *a, **kw: None
        sys.modules["sqlalchemy.orm"] = _sa_orm
        _sa_orm_attrs = types.ModuleType("sqlalchemy.orm.attributes")
        _sa_orm_attrs.flag_modified = lambda *a, **kw: None
        sys.modules["sqlalchemy.orm.attributes"] = _sa_orm_attrs
    if "sqlalchemy.dialects" not in sys.modules:
        sys.modules["sqlalchemy.dialects"] = types.ModuleType("sqlalchemy.dialects")
    if "sqlalchemy.dialects.postgresql" not in sys.modules:
        _pg = types.ModuleType("sqlalchemy.dialects.postgresql")
        _pg.JSONB = None
        _pg.UUID = lambda *a, **kw: None
        sys.modules["sqlalchemy.dialects.postgresql"] = _pg

# --- redis — real import preferred so redis.from_url stays available ---
if "redis" not in sys.modules:
    try:
        import redis
        import redis.asyncio  # noqa: F401
    except ImportError:
        sys.modules.setdefault("redis", types.ModuleType("redis"))
        sys.modules.setdefault("redis.asyncio", types.ModuleType("redis.asyncio"))

# --- pydantic_settings (falls nicht vorhanden) ---
if "pydantic_settings" not in sys.modules:
    _ps = types.ModuleType("pydantic_settings")

    class _BaseSettings:
        def __init__(self, **kw):
            pass

    _ps.BaseSettings = _BaseSettings
    sys.modules["pydantic_settings"] = _ps


# --- _FakeSettings: module-level, damit _make_app_with_db immer darauf
# verweisen kann (unabhängig davon, ob "config" schon vom conftest-Hook /
# einer anderen Testdatei gestubbt wurde). ---
class _FakeSettings:
    # Admin fields
    admin_user: str | None = None
    admin_password: str | None = None
    # W1 (2026-07-21): api/admin_auth.py::_session_secret() verlangt ein
    # dediziertes ADMIN_SESSION_SECRET, sobald app_env == "production" ODER
    # default_tenant_key == "default-key" ist (sonst RuntimeError — das Gate
    # ist gewollt, siehe admin_auth.py-Docstring). Diese Fake-Settings setzen
    # app_env="production" (Produktions-Realismus), daher MUSS hier ein
    # Secret gesetzt sein, sonst crasht jeder Test, der eine Session braucht.
    admin_session_secret: str | None = "test-admin-session-secret-32chars-min"
    cookie_secure: bool = False
    # Core
    database_url: str = "postgresql+asyncpg://t:t@localhost/t"
    sync_database_url: str = "postgresql://t:t@localhost/t"
    redis_url: str = "redis://localhost:6379/0"
    default_tenant_key: str = "default-key"
    # LLM
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    litellm_base_url: str | None = None
    litellm_api_key: str | None = None
    requesty_api_key: str | None = None
    # Nextcloud — needed by services/__init__.py → nextcloud.py at collection time
    nextcloud_url: str = ""
    nextcloud_user: str = ""
    nextcloud_password: str = ""
    # Misc
    sentry_dsn: str = ""
    app_env: str = "production"
    prompt_storage_backend: str = "localfs"
    content_truth_base_path: str = "/app/content-truth"
    content_truth_overlay_path: str = "/app/data/prompts-custom"
    telegram_bot_token: str | None = None
    telegram_admin_chat_id: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_bot_username: str | None = None
    # Throttle fields (needed when _FakeSettings lands in config.settings
    # and test_throttle_adversarial.py does patch.object(settings, ...))
    max_calls_per_tenant_per_hour: int = 200
    max_calls_global_per_hour: int = 1000


# --- config-Stub: DETERMINISTISCH sicherstellen, additiv wenn Modul schon existiert ---
_cfg = _ensure_stub("config")
_ensure_attr(_cfg, "settings", _FakeSettings)

# --- services.llm — real import preferred so downstream tests keep LLMService ---
# Real import uses the config stub above (_FakeSettings) which is safe.
# Bare stub only as last-resort fallback (no sqlalchemy, no httpx etc.).
if "services.llm" not in sys.modules:
    try:
        import services.llm  # noqa: F401
    except Exception:
        from unittest.mock import MagicMock as _MM

        _svc_llm = types.ModuleType("services.llm")
        _svc_llm.set_llm_tenant = lambda *a: None
        _svc_llm.llm_service = _MM()
        _svc_llm.LLMService = _MM
        _svc_llm._maybe_send_global_cap_alert = _MM()
        _svc_llm.BudgetExceededError = type("BudgetExceededError", (Exception,), {})
        sys.modules["services.llm"] = _svc_llm

# --- models stubs — DETERMINISTISCH statt fragiler "if not in sys.modules"-Guards. ---
# Hintergrund: tests/conftest.py::pytest_collectstart setzt models.base und
# models.tenant vor jeder Testdatei-Collection auf den echten Baseline-Zustand
# zurück (siehe conftest.py). Ein "if not in sys.modules"-Guard sieht das Modul
# dadurch mal vorhanden (Baseline), mal nicht (nach einem Fremd-Teardown) —
# nicht deterministisch. _ensure_package/_ensure_attr sind idempotent additiv:
# ein bereits reales Modul wird nicht überschrieben, nur fehlende Attribute
# werden nachgerüstet.
import os as _os

_BACKEND_DIR_AUTH = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

_models_pkg = _ensure_package("models")
if not _models_pkg.__path__:
    _models_pkg.__path__ = [_os.path.join(_BACKEND_DIR_AUTH, "models")]
    _models_pkg.__package__ = "models"

try:
    import models.base as _mb
except Exception:
    _mb = _ensure_package("models.base")
_ensure_attr(_mb, "async_session_factory", lambda: None)
_ensure_attr(_mb, "sync_session_factory", lambda: None)
_ensure_attr(_mb, "Base", lambda: object)

try:
    import models.tenant as _mt
except Exception:
    _mt = _ensure_package("models.tenant")


class _FakeTenantAuth:
    pass


_ensure_attr(_mt, "Tenant", lambda: _FakeTenantAuth)

# Pre-import model submodules so _telegram_task_env.py (loaded by
# test_idempotency_routing.py) cannot overwrite them with MagicMock() stubs.
for _mdl_name in ("models.llm_call_log", "models.llm_provider", "models.company_profile"):
    if _mdl_name not in sys.modules:
        try:
            _ilu = __import__("importlib")
            _ilu.import_module(_mdl_name)
        except Exception:
            pass  # If import fails, leave sys.modules alone (don't install bad stub)

# --- dependencies-Stub — DETERMINISTISCH sicherstellen (additiv). ---
_deps_mod_auth = _ensure_stub("dependencies")


async def _get_db_auth():
    yield None


async def _get_tenant_auth():
    return None


_ensure_attr(_deps_mod_auth, "get_db", lambda: _get_db_auth)
_ensure_attr(_deps_mod_auth, "get_tenant", lambda: _get_tenant_auth)

# ---------------------------------------------------------------------------
# Echte Imports ab hier
# ---------------------------------------------------------------------------

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Hilfs-Utilities
# ---------------------------------------------------------------------------


def _patch_settings(**kwargs):
    """Patcht api.admin_auth.settings-Attribute für einen Test."""
    return patch.multiple("api.admin_auth.settings", **kwargs)


def _fake_db_empty():
    """DB-Session-Mock der immer leere Ergebnisse liefert."""
    db = AsyncMock()
    empty = MagicMock()
    empty.fetchone.return_value = None
    empty.fetchall.return_value = []
    db.execute = AsyncMock(return_value=empty)
    db.commit = AsyncMock()
    return db


def _fake_db_with_tenant(
    tenant_id: str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    name: str = "Test-Tenant",
    api_key: str = "cap-test-12345678",
    enabled: bool = True,
):
    """DB-Mock mit einem vorhandenen Tenant (exist + dup-check + list)."""
    import datetime as _dt

    db = AsyncMock()

    exist_result = MagicMock()
    exist_result.fetchone.return_value = (tenant_id,)

    dup_result = MagicMock()
    dup_result.fetchone.return_value = None  # kein Duplikat

    list_result = MagicMock()
    list_result.fetchall.return_value = [
        (uuid.UUID(tenant_id), name, api_key, enabled, _dt.datetime(2025, 1, 1)),
    ]

    async def _execute(query, params=None):
        sql = str(query).upper()
        # Tenants-Liste (SELECT ID, NAME, API_KEY ...)
        if "NAME" in sql and "API_KEY" in sql and "FROM TENANTS" in sql:
            return list_result
        # Duplikat-Check (SELECT 1 FROM tenants WHERE api_key = ...)
        if "SELECT 1" in sql:
            return dup_result
        # Existence-Check (SELECT id FROM tenants WHERE id = ...)
        return exist_result

    db.execute = AsyncMock(side_effect=_execute)
    db.commit = AsyncMock()
    return db


def _make_app_with_db(db=None) -> FastAPI:
    """Minimale Test-App mit admin_auth-Router, DB per Override."""
    # Re-install _FakeSettings in case config was replaced/removed by other test files
    # (e.g. test_prompt_studio_api.py removes config; test_telegram_bot_api.py then
    #  installs MagicMock-based config, which causes hmac.new to fail with TypeError).
    import api.admin_auth as _admin_mod
    import dependencies
    from api.admin_auth import router

    if not isinstance(_admin_mod.settings, _FakeSettings):
        _admin_mod.settings = _FakeSettings()

    app = FastAPI()
    app.include_router(router, prefix="/api")

    if db is not None:

        async def _override_db():
            yield db

        app.dependency_overrides[dependencies.get_db] = _override_db

    return app


def _make_app() -> FastAPI:
    return _make_app_with_db()


# ---------------------------------------------------------------------------
# Tests: POST /api/admin/login
# ---------------------------------------------------------------------------


class TestAdminLogin:
    def test_login_unconfigured_returns_503(self):
        """Wenn ADMIN_USER/ADMIN_PASSWORD nicht gesetzt → 503."""
        app = _make_app()
        with _patch_settings(admin_user=None, admin_password=None):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/admin/login",
                json={"username": "admin", "password": "secret"},
            )
        assert resp.status_code == 503
        assert "konfiguriert" in resp.json()["detail"].lower()

    def test_login_wrong_credentials_returns_401(self):
        """Falsche Zugangsdaten → 401, kein User-Enumeration-Hinweis."""
        app = _make_app()
        with _patch_settings(admin_user="operator", admin_password="correct-pw"):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/admin/login",
                json={"username": "wrong", "password": "wrong"},
            )
        assert resp.status_code == 401
        detail = resp.json()["detail"]
        assert "operator" not in detail.lower(), "User-Enumeration-Leak im Fehlertext"
        assert "correct" not in detail.lower(), "Passwort im Fehlertext"

    def test_login_wrong_password_only_returns_401(self):
        """Richtiger User, falsches Passwort → 401."""
        app = _make_app()
        with _patch_settings(admin_user="operator", admin_password="correct-pw"):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/admin/login",
                json={"username": "operator", "password": "wrong-pw"},
            )
        assert resp.status_code == 401

    def test_login_correct_sets_cookie_and_returns_200(self):
        """Richtige Zugangsdaten → 200 + Set-Cookie admin_session."""
        app = _make_app()
        with _patch_settings(admin_user="operator", admin_password="correct-pw"):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/admin/login",
                json={"username": "operator", "password": "correct-pw"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["authenticated"] is True
        assert body["user"] == "operator"
        set_cookie = resp.headers.get("set-cookie", "")
        assert "admin_session" in set_cookie

    def test_login_response_does_not_leak_password(self):
        """Passwort darf NICHT in der Antwort erscheinen."""
        app = _make_app()
        with _patch_settings(admin_user="operator", admin_password="s3cr3t-pw"):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/admin/login",
                json={"username": "operator", "password": "s3cr3t-pw"},
            )
        assert "s3cr3t" not in resp.text
        assert "password" not in resp.json()

    def test_login_correct_cookie_is_httponly(self):
        """Cookie muss HttpOnly-Flag haben."""
        app = _make_app()
        with _patch_settings(admin_user="op", admin_password="pw"):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/admin/login",
                json={"username": "op", "password": "pw"},
            )
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "")
        assert "httponly" in set_cookie.lower()


# ---------------------------------------------------------------------------
# Tests: Session-Token (Unit-Tests)
# ---------------------------------------------------------------------------


class TestSessionToken:
    def test_valid_token_verifies(self):
        from api.admin_auth import _make_session, _verify_session

        token = _make_session("testuser")
        assert _verify_session(token) == "testuser"

    def test_expired_token_returns_none(self):
        from api.admin_auth import SESSION_TTL, _make_session, _verify_session

        with patch("api.admin_auth.time") as mock_time:
            mock_time.time.return_value = 1000
            token = _make_session("testuser")

        with patch("api.admin_auth.time") as mock_time:
            mock_time.time.return_value = 1000 + SESSION_TTL + 1
            result = _verify_session(token)

        assert result is None

    def test_manipulated_signature_returns_none(self):
        from api.admin_auth import _make_session, _verify_session

        token = _make_session("testuser")
        b64, _ = token.rsplit(".", 1)
        tampered = b64 + ".deadbeefdeadbeef"
        assert _verify_session(tampered) is None

    def test_truncated_token_returns_none(self):
        from api.admin_auth import _verify_session

        assert _verify_session("notavalidtoken") is None
        assert _verify_session("") is None

    def test_manipulated_payload_returns_none(self):
        """Payload verändert → Signatur stimmt nicht mehr → None."""
        import base64
        import json as _json

        from api.admin_auth import _make_session, _verify_session

        token = _make_session("testuser")
        b64, sig = token.rsplit(".", 1)
        padding = 4 - len(b64) % 4
        padded = b64 + ("=" * (padding % 4))
        payload = _json.loads(base64.urlsafe_b64decode(padded))
        payload["user"] = "attacker"
        new_b64 = base64.urlsafe_b64encode(_json.dumps(payload).encode()).rstrip(b"=").decode()
        tampered = f"{new_b64}.{sig}"
        assert _verify_session(tampered) is None


# ---------------------------------------------------------------------------
# Tests: GET /api/admin/session
# ---------------------------------------------------------------------------


class TestSessionEndpoint:
    def test_no_cookie_returns_unauthenticated(self):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/admin/session")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is False

    def test_valid_cookie_returns_authenticated(self):
        from api.admin_auth import _make_session

        app = _make_app()
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.get("/api/admin/session")
        assert resp.status_code == 200
        body = resp.json()
        assert body["authenticated"] is True
        assert body["user"] == "operator"

    def test_invalid_cookie_returns_unauthenticated(self):
        app = _make_app()
        client = TestClient(
            app, raise_server_exceptions=False, cookies={"admin_session": "garbage"}
        )
        resp = client.get("/api/admin/session")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is False


# ---------------------------------------------------------------------------
# Tests: POST /api/admin/logout
# ---------------------------------------------------------------------------


class TestLogout:
    def test_logout_clears_cookie(self):
        from api.admin_auth import _make_session

        app = _make_app()
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post("/api/admin/logout")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        set_cookie = resp.headers.get("set-cookie", "")
        assert "max-age=0" in set_cookie.lower()


# ---------------------------------------------------------------------------
# Tests: require_admin_session Dependency
# ---------------------------------------------------------------------------


class TestRequireAdminSessionDependency:
    def test_without_cookie_returns_401(self):
        """Endpoint hinter require_admin_session ohne Cookie → 401."""
        db = _fake_db_empty()
        app = _make_app_with_db(db)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/admin/users")
        assert resp.status_code == 401

    def test_with_valid_cookie_passes(self):
        from api.admin_auth import _make_session

        db = _fake_db_empty()
        app = _make_app_with_db(db)
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.get("/api/admin/users")
        # leere Liste ist ok
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tests: GET /api/admin/users
# ---------------------------------------------------------------------------


class TestUsersList:
    def test_returns_masked_api_key_not_plaintext(self):
        """api_key darf im Response NICHT im Klartext erscheinen."""
        from api.admin_auth import _make_session

        real_key = "cap-real-api-key-12345678abcdef"
        db = _fake_db_with_tenant(api_key=real_key)
        app = _make_app_with_db(db)
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.get("/api/admin/users")
        assert resp.status_code == 200
        body = resp.json()
        assert "users" in body
        for user in body["users"]:
            assert "api_key_masked" in user
            assert real_key not in str(user.get("api_key_masked", ""))

    def test_masked_key_format(self):
        """Maskiertes Format: first4...last4."""
        from api.admin_auth import _mask_key

        assert _mask_key("cap-abc12345678def") == "cap-...8def"
        assert _mask_key("abcdefghij") == "abcd...ghij"
        assert _mask_key("short") == "****"  # <8 Zeichen

    def test_response_never_contains_plaintext_key(self):
        """JSON-Response-Text darf den Klartext-Key an keiner Stelle enthalten."""
        from api.admin_auth import _make_session

        real_key = "supersecretkey1234"
        db = _fake_db_with_tenant(api_key=real_key)
        app = _make_app_with_db(db)
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.get("/api/admin/users")
        assert real_key not in resp.text


# ---------------------------------------------------------------------------
# Tests: POST /api/admin/users/{id}/regenerate-api-key
# ---------------------------------------------------------------------------


class TestRegenerateApiKey:
    def test_regenerate_returns_new_key_plaintext(self):
        """regenerate-api-key gibt neuen Key einmalig im Klartext zurück."""
        from api.admin_auth import _make_session

        tenant_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        db = _fake_db_with_tenant(tenant_id=tenant_id)
        app = _make_app_with_db(db)
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post(f"/api/admin/users/{tenant_id}/regenerate-api-key")
        assert resp.status_code == 200
        body = resp.json()
        assert "api_key" in body
        new_key = body["api_key"]
        assert isinstance(new_key, str)
        assert 0 < len(new_key) <= 64

    def test_regenerate_not_found(self):
        """Unbekannter Tenant → 404."""
        from api.admin_auth import _make_session

        db = _fake_db_empty()
        app = _make_app_with_db(db)
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post("/api/admin/users/nonexistent-id/regenerate-api-key")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: PUT /api/admin/users/{id}/api-key
# ---------------------------------------------------------------------------


class TestSetApiKey:
    def test_valid_key_accepted(self):
        """Gültiger Key → 200 + maskierter Key."""
        from api.admin_auth import _make_session

        tenant_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        db = _fake_db_with_tenant(tenant_id=tenant_id)
        app = _make_app_with_db(db)
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.put(
            f"/api/admin/users/{tenant_id}/api-key",
            json={"api_key": "valid-key-123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "api_key_masked" in body
        assert "valid-key-123" not in body["api_key_masked"]

    def test_too_long_key_rejected(self):
        """Key > 64 Zeichen → 422."""
        from api.admin_auth import _make_session

        tenant_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        db = _fake_db_with_tenant(tenant_id=tenant_id)
        app = _make_app_with_db(db)
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.put(
            f"/api/admin/users/{tenant_id}/api-key",
            json={"api_key": "a" * 65},
        )
        assert resp.status_code == 422

    def test_invalid_chars_rejected(self):
        """Key mit ungültigem Zeichen → 422."""
        from api.admin_auth import _make_session

        tenant_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        db = _fake_db_with_tenant(tenant_id=tenant_id)
        app = _make_app_with_db(db)
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.put(
            f"/api/admin/users/{tenant_id}/api-key",
            json={"api_key": "invalid@key!"},
        )
        assert resp.status_code == 422

    def test_duplicate_key_returns_409(self):
        """Bereits vergebener Key → 409."""
        from api.admin_auth import _make_session

        tenant_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        exist_result = MagicMock()
        exist_result.fetchone.return_value = (tenant_id,)

        dup_result = MagicMock()
        dup_result.fetchone.return_value = (1,)  # Duplikat

        call_counter = {"n": 0}

        async def _execute(query, params=None):
            if call_counter["n"] == 0:
                call_counter["n"] += 1
                return exist_result
            return dup_result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=_execute)
        db.commit = AsyncMock()

        app = _make_app_with_db(db)
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.put(
            f"/api/admin/users/{tenant_id}/api-key",
            json={"api_key": "already-used"},
        )
        assert resp.status_code == 409

    def test_not_found_returns_404(self):
        """Unbekannter Tenant → 404."""
        from api.admin_auth import _make_session

        db = _fake_db_empty()
        app = _make_app_with_db(db)
        token = _make_session("operator")
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.put(
            "/api/admin/users/nonexistent/api-key",
            json={"api_key": "somekey"},
        )
        assert resp.status_code == 404
