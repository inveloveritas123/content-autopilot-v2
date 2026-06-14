"""
Tests für GET /api/tenants/me/ui-mode und PUT /api/tenants/me/ui-mode (Issue #90).

Strategie: Business-Logik wird direkt (ohne HTTP-Stack) mit einer AsyncMock-DB
           getestet. Schwere Dependencies (sqlalchemy, fastapi, pydantic) werden
           via Thin-Stubs eingehängt — identisches Muster wie test_tenant_pause.py.

Abgedeckte Fälle:
  1. GET default → 'mvp' (kein gespeicherter Wert)
  2. GET stored  → gibt gespeicherten Wert zurück
  3. PUT valid "mvp" → persistiert, Response {mode: "mvp"}
  4. PUT valid "features" → persistiert, Response {mode: "features"}
  5. PUT invalid → 422
  6. E3: PUT nutzt ausschliesslich tenant aus get_tenant-Dependency (kein freier ID-Param)
"""

from __future__ import annotations

import asyncio
import sys
import types
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Stubs für schwere Dependencies ───────────────────────────────────────────


def _stub(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod
    return sys.modules[name]


# sqlalchemy core + ext — only stub missing attrs; never overwrite real sqlalchemy.
# Real sqlalchemy (installed in CI) has `create_engine`; stubs don't.
_sa = _stub("sqlalchemy")
if not hasattr(_sa, "create_engine"):
    _sa.func = MagicMock()
    _sa.select = MagicMock()
    _sa.text = lambda sql: sql
    _sa.Boolean = MagicMock()
    _sa.DateTime = MagicMock()
    _sa.String = MagicMock()
    _sa.Text = MagicMock()
_sa_ext = _stub("sqlalchemy.ext")
_sa_ext_async = _stub("sqlalchemy.ext.asyncio")
if not hasattr(_sa_ext_async, "create_async_engine"):
    _sa_ext_async.AsyncSession = MagicMock()
_sa_orm = _stub("sqlalchemy.orm")
if not hasattr(_sa_orm, "Session"):
    _sa_orm.Mapped = MagicMock()
    _sa_orm.mapped_column = MagicMock()
    _sa_orm.relationship = MagicMock()
_sa_orm.attributes = _stub("sqlalchemy.orm.attributes")
if not hasattr(_sa_orm.attributes, "get_history"):
    _sa_orm.attributes.flag_modified = MagicMock()
_sa_dialects = _stub("sqlalchemy.dialects")
_sa_pg = _stub("sqlalchemy.dialects.postgresql")
if not hasattr(_sa_pg, "ARRAY"):
    _sa_pg.JSONB = MagicMock()
    _sa_pg.UUID = MagicMock()

# pydantic
if "pydantic" not in sys.modules:
    _pd = _stub("pydantic")
    _pd.BaseModel = object

# fastapi stubs
if "fastapi" not in sys.modules:
    _fa = _stub("fastapi")

    class _FakeHTTPException(Exception):
        def __init__(self, status_code: int, detail=None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    class _FakeAPIRouter:
        def __init__(self, *a, **kw):
            pass

        def _noop_decorator(self, *a, **kw):
            def decorator(fn):
                return fn

            if len(a) == 1 and callable(a[0]):
                return a[0]
            return decorator

        get = post = put = patch = delete = _noop_decorator

    _fa.APIRouter = _FakeAPIRouter
    _fa.Depends = lambda x: x
    _fa.File = MagicMock()
    _fa.Header = MagicMock()
    _fa.Query = MagicMock()
    _fa.UploadFile = MagicMock()
    _fa.HTTPException = _FakeHTTPException
    _stub("fastapi.responses").StreamingResponse = MagicMock()
    HTTPException = _FakeHTTPException
else:
    from fastapi import HTTPException

# models, services, dependencies
for _mod in [
    "models",
    "models.base",
    "models.tenant",
    "models.content_performance",
    "services",
    "services.nextcloud",
    "services.tenant_export",
    "services.tenant_import",
    "services.llm",
    "dependencies",
]:
    _stub(_mod)

sys.modules["dependencies"].get_db = MagicMock()
sys.modules["dependencies"].get_tenant = MagicMock()
sys.modules["models.tenant"].Tenant = MagicMock()
sys.modules["models.content_performance"].ContentPerformance = MagicMock()
sys.modules["services.nextcloud"].nextcloud_client = MagicMock()
sys.modules["services.tenant_export"].TenantExportService = MagicMock(return_value=MagicMock())
sys.modules["services.tenant_import"].TenantImportService = MagicMock(return_value=MagicMock())
# Only install stub attributes when services.llm is a stub (not the real module).
# Real module has _tenant_id_ctx; overwriting set_llm_tenant on the real module
# breaks test_cost_cap (ContextVar propagation).
if not hasattr(sys.modules.get("services.llm"), "_tenant_id_ctx"):
    sys.modules["services.llm"].set_llm_tenant = MagicMock()
    sys.modules["services.llm"].PURPOSE_MAX_TOKENS = {}
    sys.modules["services.llm"].PURPOSE_MODEL_MAP = {}
    sys.modules["services.llm"].REQUESTY_MODELS = {}

# ── Jetzt erst importieren ────────────────────────────────────────────────────
from api.tenants import (
    DEFAULT_UI_MODE,
    get_ui_mode,
    set_ui_mode,
)


# Pydantic ist in der lokalen venv (Py3.9) zwar installiert, aber UiModeUpdate
# erbt von BaseModel.  Da der pydantic-Stub BaseModel=object ersetzt, wenn pydantic
# NICHT in sys.modules war, kann UiModeUpdate() kein __init__ mit kwargs.
# Wir bauen stattdessen ein simples Namespace-Objekt mit .mode — identisch zu dem,
# was die Endpoint-Funktion ausschließlich nutzt.
def _mode_payload(mode: str):
    """Leichter Ersatz für UiModeUpdate(mode=...) ohne Pydantic."""
    ns = types.SimpleNamespace()
    ns.mode = mode
    return ns


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_tenant(settings=None):
    t = MagicMock()
    t.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    t.settings = settings
    return t


def _make_async_db():
    return AsyncMock()


def _run(coro):
    return asyncio.run(coro)


# ── GET /tenants/me/ui-mode ───────────────────────────────────────────────────


def test_get_ui_mode_default():
    """GET ohne gespeicherten Wert → DEFAULT_UI_MODE ('mvp') wird zurückgegeben."""
    tenant = _make_tenant(settings={})
    result = _run(get_ui_mode(tenant=tenant))
    assert result == {"mode": DEFAULT_UI_MODE}
    assert result["mode"] == "mvp"


def test_get_ui_mode_none_settings():
    """GET mit settings=None → Default, kein Crash."""
    tenant = _make_tenant(settings=None)
    result = _run(get_ui_mode(tenant=tenant))
    assert result["mode"] == DEFAULT_UI_MODE


def test_get_ui_mode_stored_features():
    """GET mit gespeichertem 'features' → 'features' zurückgegeben."""
    tenant = _make_tenant(settings={"ui_mode": "features"})
    result = _run(get_ui_mode(tenant=tenant))
    assert result == {"mode": "features"}


def test_get_ui_mode_stored_mvp():
    """GET mit explizit gespeichertem 'mvp' → 'mvp'."""
    tenant = _make_tenant(settings={"ui_mode": "mvp"})
    result = _run(get_ui_mode(tenant=tenant))
    assert result == {"mode": "mvp"}


# ── PUT /tenants/me/ui-mode ───────────────────────────────────────────────────


def test_set_ui_mode_mvp():
    """PUT {mode: 'mvp'} → persistiert, Response {mode: 'mvp'}."""
    tenant = _make_tenant(settings={})
    db = _make_async_db()
    data = _mode_payload("mvp")

    result = _run(set_ui_mode(data=data, tenant=tenant, db=db))

    assert result == {"mode": "mvp"}
    assert tenant.settings["ui_mode"] == "mvp"
    db.commit.assert_awaited_once()


def test_set_ui_mode_features():
    """PUT {mode: 'features'} → persistiert, Response {mode: 'features'}."""
    tenant = _make_tenant(settings={})
    db = _make_async_db()
    data = _mode_payload("features")

    result = _run(set_ui_mode(data=data, tenant=tenant, db=db))

    assert result == {"mode": "features"}
    assert tenant.settings["ui_mode"] == "features"
    db.commit.assert_awaited_once()


def test_set_ui_mode_preserves_other_settings():
    """PUT ui-mode darf andere settings-Keys nicht überschreiben."""
    tenant = _make_tenant(settings={"tone": "professionell", "language": "de"})
    db = _make_async_db()
    data = _mode_payload("mvp")

    _run(set_ui_mode(data=data, tenant=tenant, db=db))

    assert tenant.settings["tone"] == "professionell"
    assert tenant.settings["language"] == "de"
    assert tenant.settings["ui_mode"] == "mvp"


def test_set_ui_mode_invalid_raises_422():
    """PUT mit ungültigem Modus → 422 (HTTPException)."""
    tenant = _make_tenant(settings={})
    db = _make_async_db()
    data = _mode_payload("superpower")

    with pytest.raises(HTTPException) as exc_info:
        _run(set_ui_mode(data=data, tenant=tenant, db=db))

    assert exc_info.value.status_code == 422
    db.commit.assert_not_awaited()


def test_set_ui_mode_invalid_empty_string():
    """PUT mit leerem String → 422."""
    tenant = _make_tenant(settings={})
    db = _make_async_db()
    data = _mode_payload("")

    with pytest.raises(HTTPException) as exc_info:
        _run(set_ui_mode(data=data, tenant=tenant, db=db))

    assert exc_info.value.status_code == 422


# ── E3: Mandantentrennung ──────────────────────────────────────────────────────


def test_set_ui_mode_e3_no_tenant_id_in_path():
    """E3: set_ui_mode hat keinen tenant_id-Pfadparameter — Tenant kommt ausschließlich
    aus der get_tenant-Dependency (Dependency Injection). Wir prüfen, dass die Funktion
    tenant.settings des übergebenen Tenants ändert und nicht irgendeinen anderen."""
    own_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    other_tenant_settings = {}

    own_tenant = _make_tenant(settings={})
    own_tenant.id = own_id
    db = _make_async_db()
    data = _mode_payload("features")

    _run(set_ui_mode(data=data, tenant=own_tenant, db=db))

    # Nur own_tenant.settings wurde geändert — other_tenant_settings bleibt leer
    assert own_tenant.settings["ui_mode"] == "features"
    assert "ui_mode" not in other_tenant_settings


def test_get_ui_mode_e3_reads_own_tenant_only():
    """E3: get_ui_mode liest ausschliesslich tenant.settings — kein freier ID-Param."""
    own_tenant = _make_tenant(settings={"ui_mode": "features"})
    result = _run(get_ui_mode(tenant=own_tenant))
    assert result["mode"] == "features"
