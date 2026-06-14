"""Tests für POST /api/admin/users — Neuen Tenant anlegen (Issue #98 Erweiterung)

Ausführung (lokal):
    cd backend && PYTHONPATH=. \
      ../../.venv/bin/python -m pytest tests/test_admin_create_user.py -q

Strategie: gleiche Stub-Technik wie test_admin_auth.py — schwere Deps werden via
sys.modules-Stubs vor dem ersten Import injiziert. Funktioniert auf Py3.9-venv
ohne installiertes sqlalchemy/celery/google.
"""

from __future__ import annotations

import sys
import types

# ---------------------------------------------------------------------------
# Stubs für fehlende Deps — müssen VOR jedem anderen Import gesetzt werden
# ---------------------------------------------------------------------------


def _maybe_stub(name: str, factory):
    """Setzt sys.modules[name] nur wenn noch nicht vorhanden."""
    if name not in sys.modules:
        sys.modules[name] = factory()


# --- sqlalchemy (real if installed, stub only as fallback) ---
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
        sa.update = lambda *a, **kw: None
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

# --- pydantic_settings ---
if "pydantic_settings" not in sys.modules:
    _ps = types.ModuleType("pydantic_settings")

    class _BaseSettings:
        def __init__(self, **kw):
            pass

    _ps.BaseSettings = _BaseSettings
    sys.modules["pydantic_settings"] = _ps


# --- _FakeSettings: defined at module level so _make_app_with_db can always reference it ---
class _FakeSettings:
    # Admin fields
    admin_user: str | None = None
    admin_password: str | None = None
    admin_session_secret: str | None = None
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
    # Nextcloud
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
    max_calls_per_tenant_per_hour: int = 200
    max_calls_global_per_hour: int = 1000


# --- config: minimaler Stub mit den benötigten Feldern ---
if "config" not in sys.modules:
    _cfg = types.ModuleType("config")

    class _FakeSettings:
        # Admin fields
        admin_user: str | None = None
        admin_password: str | None = None
        admin_session_secret: str | None = None
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
        max_calls_per_tenant_per_hour: int = 200
        max_calls_global_per_hour: int = 1000

    _cfg.settings = _FakeSettings()
    sys.modules["config"] = _cfg

# --- services.llm — real import preferred so downstream tests keep LLMService ---
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

# --- models stubs ---
# Give the models stub a real __path__ so Python can find submodules like
# models.llm_provider when services/provider_resolver.py is imported later.
import os as _os

_BACKEND_DIR_CU = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if "models" not in sys.modules:
    _models_pkg = types.ModuleType("models")
    _models_pkg.__path__ = [_os.path.join(_BACKEND_DIR_CU, "models")]
    _models_pkg.__package__ = "models"
    sys.modules["models"] = _models_pkg
elif not hasattr(sys.modules["models"], "__path__"):
    sys.modules["models"].__path__ = [_os.path.join(_BACKEND_DIR_CU, "models")]
    sys.modules["models"].__package__ = "models"

if "models.base" not in sys.modules:
    _mb = types.ModuleType("models.base")
    _mb.async_session_factory = None
    _mb.sync_session_factory = None  # needed by tasks/p03_task.py etc.
    _mb.Base = object
    sys.modules["models.base"] = _mb

# Tenant-Stub — leichtes Objekt das die nötigen Felder hat
# Always patch Tenant even if models.tenant already exists (test_admin_auth.py
# installs a bare _FakeTenant without __init__ args that crashes create_tenant).
if "models.tenant" not in sys.modules:
    _mt = types.ModuleType("models.tenant")
    sys.modules["models.tenant"] = _mt
else:
    _mt = sys.modules["models.tenant"]


class _FakeTenant:
    """Minimales ORM-Stub-Objekt für Tenant."""

    def __init__(self, *, name, api_key, slug, settings=None, enabled=True):
        import uuid as _uuid

        self.id = _uuid.uuid4()
        self.name = name
        self.api_key = api_key
        self.slug = slug
        self.settings = settings or {}
        self.enabled = enabled


_mt.Tenant = _FakeTenant

# --- dependencies stub ---
if "dependencies" not in sys.modules:
    _deps = types.ModuleType("dependencies")

    async def _get_db():
        yield None

    async def _get_tenant():
        return None

    _deps.get_db = _get_db
    _deps.get_tenant = _get_tenant
    sys.modules["dependencies"] = _deps

# ---------------------------------------------------------------------------
# Echte Imports ab hier
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Test-Helpers
# ---------------------------------------------------------------------------


def _make_db_for_create(
    *,
    api_key_dup: bool = False,
    slug_dup: bool = False,
    raise_on_commit: bool = False,
):
    """DB-Mock für POST /api/admin/users.

    Steuerparameter:
    - api_key_dup: ob SELECT 1 … api_key = :k einen Treffer liefert (→ Retry)
    - slug_dup:    ob SELECT 1 … slug = :s   einen Treffer liefert (→ Retry)
    - raise_on_commit: simuliert einen DB-Fehler beim Commit
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.refresh = AsyncMock()

    # Simuliere Abfrage-Ergebnisse
    _api_calls: dict[str, int] = {"n": 0}

    async def _execute(query, params=None):
        result = MagicMock()
        sql = str(query).upper()
        # api_key-Duplikat-Check
        if "API_KEY" in sql or "API_KEY_SECONDARY" in sql:
            if api_key_dup:
                result.fetchone.return_value = (1,)  # Duplikat
            else:
                result.fetchone.return_value = None  # kein Duplikat
        # slug-Duplikat-Check
        elif "SLUG" in sql:
            if slug_dup:
                result.fetchone.return_value = (1,)  # Duplikat
            else:
                result.fetchone.return_value = None
        else:
            result.fetchone.return_value = None
        return result

    db.execute = AsyncMock(side_effect=_execute)

    if raise_on_commit:
        db.commit = AsyncMock(side_effect=Exception("DB error"))
        db.rollback = AsyncMock()
    else:
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

    return db


def _make_app_with_db(db=None) -> FastAPI:
    """Minimale Test-App mit admin_auth-Router."""
    import sys as _sys

    # Re-install _FakeTenant in case another test file (e.g. test_cost_analytics.py)
    # reloaded models.tenant with the real SQLAlchemy Tenant between collection and run.
    _sys.modules["models.tenant"].Tenant = _FakeTenant
    if "api.admin_auth" in _sys.modules:
        _sys.modules["api.admin_auth"].Tenant = _FakeTenant

    # Re-install _FakeSettings in case config was replaced/removed by other test files
    # (e.g. test_telegram_bot_api.py installs MagicMock-based config after earlier
    #  test files remove config from sys.modules during their cleanup).
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


def _get_session_cookie() -> str:
    """Erzeugt einen gültigen Session-Token für Tests."""
    from api.admin_auth import _make_session

    return _make_session("operator")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateTenant:
    def test_create_without_session_returns_401(self):
        """POST /api/admin/users ohne Session → 401."""
        db = _make_db_for_create()
        app = _make_app_with_db(db)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/admin/users", json={"name": "Test GmbH"})
        assert resp.status_code == 401

    def test_create_with_session_returns_201_and_api_key(self):
        """POST /api/admin/users mit Session → 201, Antwort enthält api_key (Klartext)."""
        db = _make_db_for_create()
        app = _make_app_with_db(db)
        token = _get_session_cookie()
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post("/api/admin/users", json={"name": "Acme GmbH"})
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["name"] == "Acme GmbH"
        assert "slug" in body
        assert "api_key" in body
        key = body["api_key"]
        assert isinstance(key, str)
        assert 0 < len(key) <= 64
        # Slug sollte von Name abgeleitet sein
        assert "acme" in body["slug"]

    def test_create_empty_name_returns_422(self):
        """Leerer name → 422."""
        db = _make_db_for_create()
        app = _make_app_with_db(db)
        token = _get_session_cookie()
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post("/api/admin/users", json={"name": ""})
        assert resp.status_code == 422

    def test_create_whitespace_only_name_returns_422(self):
        """Nur Whitespace → 422."""
        db = _make_db_for_create()
        app = _make_app_with_db(db)
        token = _get_session_cookie()
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post("/api/admin/users", json={"name": "   "})
        assert resp.status_code == 422

    def test_create_name_too_long_returns_422(self):
        """name > 255 Zeichen → 422."""
        db = _make_db_for_create()
        app = _make_app_with_db(db)
        token = _get_session_cookie()
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post("/api/admin/users", json={"name": "a" * 256})
        assert resp.status_code == 422

    def test_create_duplicate_name_gets_unique_slug(self):
        """Doppelter Name → unterschiedlicher Slug (kein 500, kein 409 nach erstem Versuch).

        Beim ersten slug-Check gibt DB Treffer zurück (slug belegt),
        beim zweiten slug-Check (Suffix -2) gibt DB keinen Treffer.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.refresh = AsyncMock()
        db.rollback = AsyncMock()
        db.commit = AsyncMock()

        slug_call_count = {"n": 0}

        async def _execute(query, params=None):
            result = MagicMock()
            sql = str(query).upper()
            if "SLUG" in sql:
                slug_call_count["n"] += 1
                if slug_call_count["n"] == 1:
                    # Erster Versuch: slug belegt
                    result.fetchone.return_value = (1,)
                else:
                    # Zweiter Versuch: slug frei
                    result.fetchone.return_value = None
            else:
                # api_key-Check: immer frei
                result.fetchone.return_value = None
            return result

        db.execute = AsyncMock(side_effect=_execute)

        app = _make_app_with_db(db)
        token = _get_session_cookie()
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post("/api/admin/users", json={"name": "Acme GmbH"})
        assert resp.status_code == 201, f"Erwartet 201, got {resp.status_code}: {resp.text}"
        body = resp.json()
        # Slug muss Suffix enthalten (z.B. acme-gmbh-2)
        assert body["slug"].endswith("-2") or "-" in body["slug"]

    def test_create_slug_derived_from_name(self):
        """Slug wird korrekt aus Name abgeleitet (Kleinbuchstaben, Bindestrich)."""
        db = _make_db_for_create()
        app = _make_app_with_db(db)
        token = _get_session_cookie()
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post("/api/admin/users", json={"name": "Müller & Söhne GmbH"})
        assert resp.status_code == 201
        slug = resp.json()["slug"]
        # Slug darf keine Großbuchstaben und kein & enthalten
        assert slug == slug.lower()
        assert "&" not in slug

    def test_create_api_key_length_valid(self):
        """Generierter API-Key ist ≤64 Zeichen."""
        db = _make_db_for_create()
        app = _make_app_with_db(db)
        token = _get_session_cookie()
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post("/api/admin/users", json={"name": "Test Tenant"})
        assert resp.status_code == 201
        key = resp.json()["api_key"]
        assert len(key) <= 64

    def test_create_response_contains_all_fields(self):
        """Response enthält id, name, slug, api_key."""
        db = _make_db_for_create()
        app = _make_app_with_db(db)
        token = _get_session_cookie()
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post("/api/admin/users", json={"name": "Vollständig GmbH"})
        assert resp.status_code == 201
        body = resp.json()
        for field in ("id", "name", "slug", "api_key"):
            assert field in body, f"Feld '{field}' fehlt in Response"

    def test_create_db_commit_error_returns_409(self):
        """DB-Fehler beim Commit → 409 (Unique-Konflikt-Handling)."""
        db = _make_db_for_create(raise_on_commit=True)
        app = _make_app_with_db(db)
        token = _get_session_cookie()
        client = TestClient(app, raise_server_exceptions=False, cookies={"admin_session": token})
        resp = client.post("/api/admin/users", json={"name": "Fehler GmbH"})
        assert resp.status_code == 409
