"""Tests für dependencies._resolve_tenant (Highlander-Integration, 2026-08-14).

Nähte-Fund: get_tenant/get_tenant_id prüften bisher NUR den X-Api-Key-Header.
Der Session-Login (api/auth.py) schützte nur seinen eigenen /auth/me-Endpunkt —
wer den API-Key kennt, kam auf jede Business-Route, auch ohne eingeloggt zu
sein. Fix: bei gültigem Session-Cookie wird zusätzlich user_may_access_tenant
geprüft; ohne Cookie bleibt reine Key-Prüfung (Breaking-Change-Schutz für den
externen Cowork/Bauleiter-Consumer, README-COWORK-INTEGRATION.md).

Ausführung (lokal):
    cd backend && ../.venv/bin/python -m pytest tests/test_dependencies_session_tenant.py -q
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dependencies import _resolve_tenant

TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
API_KEY = "cap-test-key-2026"


def _make_tenant() -> MagicMock:
    t = MagicMock()
    t.id = TENANT_ID
    t.api_key = API_KEY
    t.api_key_secondary = None
    t.enabled = True
    return t


def _make_user(is_active: bool = True) -> MagicMock:
    u = MagicMock()
    u.id = "user-1"
    u.is_active = is_active
    u.role = "member"
    return u


def _make_request(cookie: str | None) -> MagicMock:
    req = MagicMock()
    req.cookies = {"cap_session": cookie} if cookie else {}
    return req


def _db_returning(scalar_result) -> AsyncMock:
    """DB-Mock: db.execute(...).scalar_one_or_none() liefert scalar_result."""
    db = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = scalar_result
    db.execute = AsyncMock(return_value=exec_result)
    return db


class TestNoCookie:
    """Ohne Session-Cookie: reine API-Key-Prüfung wie bisher (externe Consumer)."""

    @pytest.mark.asyncio
    async def test_no_cookie_resolves_by_api_key_only(self):
        tenant = _make_tenant()
        db = _db_returning(tenant)
        req = _make_request(cookie=None)

        result = await _resolve_tenant(req, API_KEY, db)

        assert result is tenant

    @pytest.mark.asyncio
    async def test_no_cookie_invalid_api_key_raises_401(self):
        db = _db_returning(None)
        req = _make_request(cookie=None)

        with pytest.raises(Exception) as exc_info:
            await _resolve_tenant(req, "wrong-key", db)
        assert getattr(exc_info.value, "status_code", None) == 401


class TestValidCookie:
    """Mit gültigem Session-Cookie: Zugriff wird zusätzlich per User geprüft."""

    @pytest.mark.asyncio
    async def test_valid_cookie_and_authorized_user_resolves_tenant(self):
        tenant = _make_tenant()
        user = _make_user()

        async def _execute(stmt):
            result = MagicMock()
            # Erster Call: User-Lookup. Zweiter Call (in _resolve_tenant_by_api_key): Tenant-Lookup.
            result.scalar_one_or_none.return_value = (
                user if _execute.calls == 0 else tenant
            )
            _execute.calls += 1
            return result

        _execute.calls = 0
        db = AsyncMock()
        db.execute = _execute

        req = _make_request(cookie="valid-cookie")

        with (
            patch("dependencies.auth_svc.verify_session", return_value="user-1"),
            patch("dependencies.auth_svc.user_may_access_tenant", new=AsyncMock(return_value=True)),
        ):
            result = await _resolve_tenant(req, API_KEY, db)

        assert result is tenant

    @pytest.mark.asyncio
    async def test_valid_cookie_but_unauthorized_user_raises_403(self):
        tenant = _make_tenant()
        user = _make_user()

        async def _execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = (
                user if _execute.calls == 0 else tenant
            )
            _execute.calls += 1
            return result

        _execute.calls = 0
        db = AsyncMock()
        db.execute = _execute

        req = _make_request(cookie="valid-cookie")

        with (
            patch("dependencies.auth_svc.verify_session", return_value="user-1"),
            patch("dependencies.auth_svc.user_may_access_tenant", new=AsyncMock(return_value=False)),
        ):
            with pytest.raises(Exception) as exc_info:
                await _resolve_tenant(req, API_KEY, db)
        assert getattr(exc_info.value, "status_code", None) == 403

    @pytest.mark.asyncio
    async def test_inactive_user_falls_back_to_api_key_only(self):
        """Ein deaktivierter User darf sich nicht per altem Cookie einschleichen —
        Fallback auf reine Key-Prüfung (kein 403, kein impliziter Zugriff)."""
        tenant = _make_tenant()
        user = _make_user(is_active=False)

        async def _execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = (
                user if _execute.calls == 0 else tenant
            )
            _execute.calls += 1
            return result

        _execute.calls = 0
        db = AsyncMock()
        db.execute = _execute

        req = _make_request(cookie="stale-cookie")

        with patch("dependencies.auth_svc.verify_session", return_value="user-1"):
            result = await _resolve_tenant(req, API_KEY, db)

        assert result is tenant


class TestInvalidCookie:
    """Abgelaufenes/manipuliertes Cookie darf nicht crashen — Fallback auf Key."""

    @pytest.mark.asyncio
    async def test_expired_or_tampered_cookie_falls_back_to_api_key(self):
        tenant = _make_tenant()
        db = _db_returning(tenant)
        req = _make_request(cookie="garbage")

        with patch("dependencies.auth_svc.verify_session", return_value=None):
            result = await _resolve_tenant(req, API_KEY, db)

        assert result is tenant
