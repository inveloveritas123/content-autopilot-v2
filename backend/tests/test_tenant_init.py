"""Tests fuer GET /api/tenant-init (Issue #157)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Minimal FastAPI app fixture — isoliert von der vollen main.py
# ---------------------------------------------------------------------------

def _make_app(tenant_fixture):
    """Erstellt eine Test-App mit gemocktem get_tenant."""
    from fastapi import FastAPI
    from api.tenant_init import router

    app = FastAPI()

    async def _override_get_tenant():
        return tenant_fixture

    from dependencies import get_tenant
    app.dependency_overrides[get_tenant] = _override_get_tenant
    app.include_router(router, prefix="/api")
    return app


def _fake_tenant(name="Test-Tenant"):
    t = MagicMock()
    t.id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    t.name = name
    t.api_key = "cap-test-abc123"
    t.enabled = True
    t.disabled_reason = None
    t.disabled_at = None
    return t


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTenantInitEndpoint:
    def test_returns_tenant_data_on_valid_key(self):
        tenant = _fake_tenant()
        app = _make_app(tenant)
        client = TestClient(app)

        resp = client.get("/api/tenant-init", headers={"X-API-Key": "cap-test-abc123"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_key"] == "cap-test-abc123"
        assert body["tenant_id"] == "12345678-1234-5678-1234-567812345678"
        assert body["tenant_name"] == "Test-Tenant"

    def test_tenant_key_present_in_response(self):
        """Stellt sicher dass der Key-Roundtrip funktioniert."""
        tenant = _fake_tenant(name="Zukunftsbund")
        app = _make_app(tenant)
        client = TestClient(app)

        resp = client.get("/api/tenant-init", headers={"X-API-Key": "cap-test-abc123"})

        assert resp.status_code == 200
        body = resp.json()
        assert "tenant_key" in body
        assert "tenant_id" in body
        assert "tenant_name" in body

    def test_missing_api_key_returns_422(self):
        """Ohne X-API-Key Header muss FastAPI 422 zurueckgeben."""
        tenant = _fake_tenant()
        # Kein Override — echte Dependency wird getriggert, Header fehlt
        from fastapi import FastAPI
        from api.tenant_init import router

        app = FastAPI()
        app.include_router(router, prefix="/api")
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/api/tenant-init")
        # FastAPI gibt 422 bei fehlendem Pflicht-Header
        assert resp.status_code == 422

    def test_no_hardcoded_tenant_key_in_module(self):
        """Stellt sicher dass kein 'cap-tenant-' String im tenant_init-Modul hardcodiert ist."""
        import importlib.util, pathlib
        src = pathlib.Path(__file__).parent.parent / "api" / "tenant_init.py"
        code = src.read_text()
        assert "cap-tenant-" not in code, (
            "Hardcodierter Tenant-Key in api/tenant_init.py gefunden!"
        )
