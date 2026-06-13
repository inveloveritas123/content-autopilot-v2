"""
Tests für /api/tenants/me/pause, /api/tenants/me/resume,
         /api/tenants/me/automation-status  (Issue #89)

Strategie: Business-Logik der drei Endpoints wird direkt (ohne HTTP-Stack)
           mit einer AsyncMock-DB getestet.  Weil die lokale venv (Py 3.9)
           kein SQLAlchemy hat, werden sqlalchemy & alle weiteren schweren
           Module als Thin-Stubs vorab in sys.modules eingehängt — nach dem
           Muster des bestehenden conftest.py.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Stubs für schwere Dependencies (Py3.9-lokal fehlen sqlalchemy etc.) ──────

def _stub(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod
    return sys.modules[name]


# sqlalchemy core + ext
_sa = _stub("sqlalchemy")
_sa.func = MagicMock()
_sa.select = MagicMock()
_sa.text = lambda sql: sql           # text() gibt den SQL-String zurück — ausreichend für unsere Tests
_sa.Boolean = MagicMock()
_sa.DateTime = MagicMock()
_sa.String = MagicMock()
_sa.Text = MagicMock()
_sa_ext = _stub("sqlalchemy.ext")
_sa_ext_async = _stub("sqlalchemy.ext.asyncio")
_sa_ext_async.AsyncSession = MagicMock()
_sa_orm = _stub("sqlalchemy.orm")
_sa_orm.Mapped = MagicMock()
_sa_orm.mapped_column = MagicMock()
_sa_orm.relationship = MagicMock()
_sa_orm.attributes = _stub("sqlalchemy.orm.attributes")
_sa_orm.attributes.flag_modified = MagicMock()
_sa_dialects = _stub("sqlalchemy.dialects")
_sa_pg = _stub("sqlalchemy.dialects.postgresql")
_sa_pg.JSONB = MagicMock()
_sa_pg.UUID = MagicMock()

# pydantic (kann installiert sein oder auch nicht — Stub schadet nicht)
if "pydantic" not in sys.modules:
    _pd = _stub("pydantic")
    _pd.BaseModel = object

# fastapi stubs — nur die Teile die tenants.py braucht
if "fastapi" not in sys.modules:
    _fa = _stub("fastapi")

    class _FakeHTTPException(Exception):
        def __init__(self, status_code: int, detail=None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    class _FakeAPIRouter:
        """APIRouter-Stub: Decorators geben Funktion unverändert zurück."""
        def __init__(self, *a, **kw):
            pass
        def _noop_decorator(self, *a, **kw):
            def decorator(fn):
                return fn
            # Falls ohne Klammern benutzt
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
    from fastapi import HTTPException  # noqa: E402

# models, services, dependencies — minimale Stubs
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
sys.modules["services.llm"].set_llm_tenant = MagicMock()
sys.modules["services.llm"].PURPOSE_MAX_TOKENS = {}
sys.modules["services.llm"].PURPOSE_MODEL_MAP = {}
sys.modules["services.llm"].REQUESTY_MODELS = {}

# ── Jetzt erst importieren ────────────────────────────────────────────────────
from api.tenants import get_automation_status, pause_automation, resume_automation  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_tenant(enabled: bool = True, disabled_at=None, disabled_reason=None):
    t = MagicMock()
    t.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    t.enabled = enabled
    t.disabled_at = disabled_at
    t.disabled_reason = disabled_reason
    return t


def _make_async_db(raise_exc=None):
    db = AsyncMock()
    if raise_exc:
        db.execute.side_effect = raise_exc
    return db


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── automation-status ─────────────────────────────────────────────────────────


def test_automation_status_enabled():
    """GET automation-status → enabled=true, paused=false wenn Tenant aktiv."""
    tenant = _make_tenant(enabled=True)
    result = _run(get_automation_status(tenant=tenant))

    assert result["enabled"] is True
    assert result["paused"] is False
    assert result["disabled_at"] is None
    assert result["disabled_reason"] is None


def test_automation_status_paused():
    """GET automation-status → enabled=false, paused=true wenn Tenant deaktiviert."""
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    tenant = _make_tenant(enabled=False, disabled_at=dt, disabled_reason="dashboard-pause")
    result = _run(get_automation_status(tenant=tenant))

    assert result["enabled"] is False
    assert result["paused"] is True
    assert result["disabled_at"] == dt.isoformat()
    assert result["disabled_reason"] == "dashboard-pause"


# ── pause ─────────────────────────────────────────────────────────────────────


def test_pause_sets_enabled_false():
    """POST pause → UPDATE + INSERT werden abgesetzt, Response hat enabled=False."""
    tenant = _make_tenant(enabled=True)
    db = _make_async_db()

    result = _run(pause_automation(tenant=tenant, db=db))

    assert result["enabled"] is False
    assert result["status"] == "paused"
    assert result["disabled_reason"] == "dashboard-pause"
    assert db.execute.call_count == 2
    db.commit.assert_awaited_once()


def test_pause_writes_audit_row():
    """POST pause → zweiter execute-Call enthält kill_switch-Audit mit action=pause."""
    tenant = _make_tenant(enabled=True)
    db = _make_async_db()

    _run(pause_automation(tenant=tenant, db=db))

    second_call = db.execute.call_args_list[1]
    sql_arg = str(second_call.args[0])
    params = second_call.args[1]
    assert "setup_pipeline_run" in sql_arg
    assert "kill_switch" in sql_arg
    assert params["tid"] == str(tenant.id)
    meta = json.loads(params["meta"])
    assert meta["action"] == "pause"
    assert meta["by"] == "self"


def test_pause_db_error_raises_500():
    """Bei DB-Fehler muss pause HTTP 500 werfen (kein stiller Erfolg)."""
    tenant = _make_tenant(enabled=True)
    db = _make_async_db(raise_exc=Exception("connection refused"))

    with pytest.raises(HTTPException) as exc_info:
        _run(pause_automation(tenant=tenant, db=db))

    assert exc_info.value.status_code == 500


# ── resume ────────────────────────────────────────────────────────────────────


def test_resume_sets_enabled_true():
    """POST resume → UPDATE + INSERT werden abgesetzt, Response hat enabled=True."""
    tenant = _make_tenant(enabled=False)
    db = _make_async_db()

    result = _run(resume_automation(tenant=tenant, db=db))

    assert result["enabled"] is True
    assert result["status"] == "active"
    assert result["disabled_at"] is None
    assert result["disabled_reason"] is None
    assert db.execute.call_count == 2
    db.commit.assert_awaited_once()


def test_resume_writes_audit_row():
    """POST resume → zweiter execute-Call enthält Audit mit action=resume."""
    tenant = _make_tenant(enabled=False)
    db = _make_async_db()

    _run(resume_automation(tenant=tenant, db=db))

    second_call = db.execute.call_args_list[1]
    sql_arg = str(second_call.args[0])
    params = second_call.args[1]
    assert "setup_pipeline_run" in sql_arg
    meta = json.loads(params["meta"])
    assert meta["action"] == "resume"
    assert meta["by"] == "self"


def test_resume_db_error_raises_500():
    """Bei DB-Fehler muss resume HTTP 500 werfen."""
    tenant = _make_tenant(enabled=False)
    db = _make_async_db(raise_exc=Exception("timeout"))

    with pytest.raises(HTTPException) as exc_info:
        _run(resume_automation(tenant=tenant, db=db))

    assert exc_info.value.status_code == 500


# ── E3 Mandantentrennung ──────────────────────────────────────────────────────


def test_pause_uses_own_tenant_id_only():
    """E3: pause nutzt ausschliesslich tenant.id aus Dependency — kein Pfad-Parameter.

    Die 'id'-Spalte im Audit-INSERT enthält eine neue uuid4 (row-PK), nicht die Tenant-ID.
    Der Tenant-Bezug liegt in 'tid' (tenant_id) und im UPDATE-Parameter 'id' (WHERE id=:id).
    Wir prüfen: other_id taucht nirgends auf; 'tid' zeigt auf own_id.
    """
    own_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    other_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    tenant = _make_tenant(enabled=True)
    tenant.id = own_id
    db = _make_async_db()

    _run(pause_automation(tenant=tenant, db=db))

    for call in db.execute.call_args_list:
        params = call.args[1] if len(call.args) > 1 else {}
        # other_id darf nirgends vorkommen
        for v in params.values():
            assert str(other_id) not in str(v), (
                f"Fremde Tenant-ID {other_id} in DB-Call — E3-Verletzung!"
            )
    # UPDATE-Call: WHERE id=:id muss own_id sein
    update_params = db.execute.call_args_list[0].args[1]
    assert str(update_params["id"]) == str(own_id)
    # Audit-INSERT: tid muss own_id sein
    audit_params = db.execute.call_args_list[1].args[1]
    assert str(audit_params["tid"]) == str(own_id)


def test_resume_uses_own_tenant_id_only():
    """E3: resume nutzt ausschliesslich tenant.id aus Dependency."""
    own_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    other_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    tenant = _make_tenant(enabled=False)
    tenant.id = own_id
    db = _make_async_db()

    _run(resume_automation(tenant=tenant, db=db))

    for call in db.execute.call_args_list:
        params = call.args[1] if len(call.args) > 1 else {}
        for v in params.values():
            assert str(other_id) not in str(v), (
                f"Fremde Tenant-ID {other_id} in DB-Call — E3-Verletzung!"
            )
