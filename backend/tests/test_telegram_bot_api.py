"""Tests for backend/api/telegram_bots.py — tenant self-service bot management.

Coverage:
- GET  not-configured     → {configured: false, online: false, …}  HTTP 200
- GET  configured         → {configured: true, status: 'active', …} HTTP 200
- POST bad token format   → 400 "Ungültiges Token-Format"
- POST getMe rejected     → 400 "Token von Telegram abgelehnt"
- POST getMe ok           → 201, status='active', token NOT in response
- DELETE configured       → 200 {status: "revoked"}
- DELETE not-configured   → 200 {status: "revoked"}  (idempotent)
- E3   only own tenant_id used in SQL (never from path)
- Token never appears in any response body

Run:
    cd backend && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_telegram_bot_api.py -q

If heavy deps (sqlalchemy, httpx, cryptography) are missing in the local venv the
tests are expected to be collected-error/skipped — see MEMORY.md constraint.
"""

from __future__ import annotations

import sys
import types
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Python 3.9 compat: datetime.UTC was added in 3.11
UTC = UTC

# ---------------------------------------------------------------------------
# Minimal stubs for unavailable heavy dependencies
# ---------------------------------------------------------------------------

# Names this module injects into sys.modules. Tracked so we can remove them again
# once the module under test is imported — otherwise these stubs leak into later
# test modules collected in the same interpreter (see cleanup note below the
# import). Only names we actually create are recorded; pre-existing real modules
# are never touched.
_STUBBED_MODULES: list[str] = []


def _stub(name: str) -> types.ModuleType:
    """Return existing module or create a blank stub in sys.modules."""
    if name not in sys.modules:
        m = types.ModuleType(name)
        sys.modules[name] = m
        _STUBBED_MODULES.append(name)
    return sys.modules[name]


# sqlalchemy stubs — only injected when sqlalchemy is not installed
try:
    import sqlalchemy as _sa_real  # noqa: F401
except ImportError:
    sa = _stub("sqlalchemy")
    sa.text = lambda q: q  # text() is a no-op pass-through
    sa.select = MagicMock()
    sa.func = MagicMock()
    _stub("sqlalchemy.ext")
    sa_async = _stub("sqlalchemy.ext.asyncio")
    sa_async.AsyncSession = MagicMock  # must be a class, not instance
    sa_async.create_async_engine = MagicMock()
    _stub("sqlalchemy.orm")
    _stub("sqlalchemy.dialects")
    _stub("sqlalchemy.dialects.postgresql")

# cryptography stubs — only injected when cryptography is not installed
try:
    from cryptography.fernet import Fernet as _Fernet_real  # noqa: F401
except ImportError:
    _crypt = _stub("cryptography")
    _crypt_fernet = _stub("cryptography.fernet")
    _crypt_fernet.Fernet = MagicMock
    _crypt_fernet.InvalidToken = Exception

# httpx is available in the local venv — do NOT stub it; starlette.testclient needs it

# ---------------------------------------------------------------------------
# Fake settings & dependency modules (must be in place BEFORE importing the router)
# ---------------------------------------------------------------------------

_FAKE_TENANT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_OTHER_TENANT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")

_fake_settings = MagicMock()
_fake_settings.default_tenant_key = "test-key-32-bytes-padding-xxxxxx"
_fake_settings.database_url = "postgresql+asyncpg://stub:stub@localhost/stub_db"
# NOTE: sync_database_url must be a valid string too — this MagicMock leaks into
# sys.modules["config"] for the rest of the pytest process (no teardown across
# test files; see tests/conftest.py doc-comment on cross-file pollution). If
# left unset, any other module that later does `create_engine(settings.sync_
# database_url)` (e.g. models/base.py) receives an auto-vivified child MagicMock
# instead of a string, which crashes deep in sqlalchemy's URL/plugin parsing
# with `ValueError: not enough values to unpack (expected 3, got 0)`.
_fake_settings.sync_database_url = "postgresql://stub:stub@localhost/stub_db"

# Stub config module
config_stub = types.SimpleNamespace(settings=_fake_settings)
if "config" not in sys.modules:
    sys.modules["config"] = config_stub  # type: ignore[assignment]
    _STUBBED_MODULES.append("config")

# Stub services.crypto — we want deterministic behaviour without real Fernet
_crypto_mod = _stub("services.crypto")
_crypto_mod.encrypt_secret = lambda plaintext, *, salt: f"ENC[{plaintext[:6]}…]"
_crypto_mod.decrypt_secret = lambda token, *, salt: "1234567:FAKETOKEN_DECRYPTED_AAABBBCCC"
_crypto_mod.mask_secret = lambda p: "1234…CCCC" if p else None

# Stub dependencies module
_deps_mod = _stub("dependencies")


async def _get_db_stub():
    """Yield a dummy AsyncSession (overridden in each test via Depends override)."""
    yield MagicMock()


async def _get_tenant_id_stub() -> uuid.UUID:
    return _FAKE_TENANT_ID


_deps_mod.get_db = _get_db_stub
_deps_mod.get_tenant_id = _get_tenant_id_stub

# Stub models.base (imported transitively)
_base_mod = _stub("models.base")
_base_mod.async_session_factory = MagicMock()
_base_mod.sync_session_factory = MagicMock()
_stub("models")
_stub("models.tenant")

# Stub services.llm (imported by dependencies transitively)
_llm_mod = _stub("services.llm")
# Guard: only overwrite set_llm_tenant on stub modules, never on the real module.
# The real module has BudgetExceededError; overwriting set_llm_tenant with MagicMock
# prevents _tenant_id_ctx from being set, breaking cost_cap and throttle tests.
if not hasattr(_llm_mod, "BudgetExceededError"):
    _llm_mod.set_llm_tenant = MagicMock()
_llm_mod.llm_service = MagicMock()  # services/__init__.py does `from .llm import llm_service`

# ---------------------------------------------------------------------------
# Import the module under test AFTER stubs are in place
# ---------------------------------------------------------------------------

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.telegram_bots as bot_module

# Restore sys.modules isolation: the stubs above only needed to be in place while
# importing the module under test. `bot_module` already holds its bound references
# (router, get_db, get_tenant_id used in the dependency overrides below), so the
# stubs can be removed now. Leaving them installed leaks into later-collected test
# modules in the same interpreter — e.g. test_telegram_outbound_pertenant.py, whose
# api/telegram.py imports `get_tenant`, a name our `dependencies` stub omits. Mirrors
# the cleanup pattern documented in test_prompt_studio_api.py.
for _name in _STUBBED_MODULES:
    sys.modules.pop(_name, None)

# Build minimal test app
_app = FastAPI()
_app.include_router(bot_module.router, prefix="/api")

# ── Dependency overrides ──────────────────────────────────────────────────


def _override_tenant_id(tid: uuid.UUID = _FAKE_TENANT_ID):
    async def _dep():
        return tid

    return _dep


def _override_db(session: MagicMock):
    async def _dep():
        yield session

    return _dep


# Shared test client (dependency overrides are applied per-test via context managers)
client = TestClient(_app, raise_server_exceptions=False)

# Convenience API URL
_URL = "/api/tenants/me/telegram-bot"
_VALID_TOKEN = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefg"  # matches regex


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_empty_db_session() -> MagicMock:
    """Async DB session stub that returns nothing from all queries."""
    session = MagicMock()
    # mappings().fetchone() → None (no row found)
    session.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))
        )
    )
    session.commit = AsyncMock()
    return session


def _make_configured_db_session(
    *,
    status: str = "active",
    validated_at: datetime | None = None,
    last_active_at: datetime | None = None,
    last_error: str | None = None,
    token_encrypted: str = "ENC[123456…]",
) -> MagicMock:
    """Return a DB session stub that returns a configured bot row."""
    row = {
        "telegram_bot_token_encrypted": token_encrypted,
        "telegram_bot_id": 9999999,
        "telegram_bot_username": "mybot",
        "telegram_bot_status": status,
        "telegram_validated_at": validated_at or datetime.now(UTC),
        "telegram_last_active_at": last_active_at,
        "telegram_revoked_at": None,
        "telegram_last_error": last_error,
    }
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=MagicMock(fetchone=MagicMock(return_value=row)))
        )
    )
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# GET — not configured
# ---------------------------------------------------------------------------


def test_get_not_configured_returns_200_with_configured_false():
    db = _make_empty_db_session()
    _app.dependency_overrides[bot_module.get_tenant_id] = _override_tenant_id()
    _app.dependency_overrides[bot_module.get_db] = _override_db(db)
    try:
        resp = client.get(_URL, headers={"X-API-Key": "test-key"})
    finally:
        _app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["online"] is False
    assert body["bot_username"] is None
    assert body["bot_id"] is None
    assert body["status"] is None
    assert body["last_active_at"] is None
    assert body["validated_at"] is None
    assert body["last_error"] is None


# ---------------------------------------------------------------------------
# GET — configured and active (online check: validated_at within 15 min)
# ---------------------------------------------------------------------------


def test_get_configured_active_returns_online_true():
    db = _make_configured_db_session(
        status="active",
        validated_at=datetime.now(UTC),
    )
    _app.dependency_overrides[bot_module.get_tenant_id] = _override_tenant_id()
    _app.dependency_overrides[bot_module.get_db] = _override_db(db)
    try:
        resp = client.get(_URL, headers={"X-API-Key": "test-key"})
    finally:
        _app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["status"] == "active"
    assert body["online"] is True
    assert body["bot_username"] == "mybot"
    # Token must NOT appear anywhere in the response
    assert "token" not in str(body).lower() or _check_no_token_leaked(body)


def _check_no_token_leaked(body: dict) -> bool:
    """Verify the raw token substring never appears in response values."""
    raw = _VALID_TOKEN.split(":")[1]  # the secret part after ':'
    return raw not in str(body)


# ---------------------------------------------------------------------------
# GET — configured but revoked (online = False)
# ---------------------------------------------------------------------------


def test_get_revoked_returns_online_false():
    db = _make_configured_db_session(status="revoked", token_encrypted="ENC[123456…]")
    _app.dependency_overrides[bot_module.get_tenant_id] = _override_tenant_id()
    _app.dependency_overrides[bot_module.get_db] = _override_db(db)
    try:
        resp = client.get(_URL, headers={"X-API-Key": "test-key"})
    finally:
        _app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["online"] is False


# ---------------------------------------------------------------------------
# POST — bad token format → 400
# ---------------------------------------------------------------------------


def test_post_bad_format_returns_400():
    db = _make_empty_db_session()
    _app.dependency_overrides[bot_module.get_tenant_id] = _override_tenant_id()
    _app.dependency_overrides[bot_module.get_db] = _override_db(db)
    try:
        resp = client.post(
            _URL,
            json={"token": "NOT_A_REAL_TOKEN"},
            headers={"X-API-Key": "test-key"},
        )
    finally:
        _app.dependency_overrides.clear()

    assert resp.status_code == 400
    body = resp.json()
    assert "Ungültiges Token-Format" in body.get("detail", "")
    # Token value must not appear in response
    assert "NOT_A_REAL_TOKEN" not in str(body)


# ---------------------------------------------------------------------------
# POST — getMe rejected → 400
# ---------------------------------------------------------------------------


def test_post_get_me_rejected_returns_400():
    db = _make_empty_db_session()
    _app.dependency_overrides[bot_module.get_tenant_id] = _override_tenant_id()
    _app.dependency_overrides[bot_module.get_db] = _override_db(db)
    try:
        with patch.object(bot_module, "_telegram_get_me", new=AsyncMock(return_value=None)):
            resp = client.post(
                _URL,
                json={"token": _VALID_TOKEN},
                headers={"X-API-Key": "test-key"},
            )
    finally:
        _app.dependency_overrides.clear()

    assert resp.status_code == 400
    body = resp.json()
    assert "Token von Telegram abgelehnt" in body.get("detail", "")
    # Token must not appear in body
    assert _VALID_TOKEN not in str(body)


# ---------------------------------------------------------------------------
# POST — getMe ok → 201, status active, token NOT in response
# ---------------------------------------------------------------------------


def test_post_get_me_ok_returns_201_active():
    # After upsert the re-fetch returns a configured row
    _bot_row = {
        "telegram_bot_token_encrypted": "ENC[123456…]",
        "telegram_bot_id": 1234567890,
        "telegram_bot_username": "mybot",
        "telegram_bot_status": "active",
        "telegram_validated_at": datetime.now(UTC),
        "telegram_last_active_at": None,
        "telegram_revoked_at": None,
        "telegram_last_error": None,
    }

    # execute call 1 (upsert) returns a plain mock; call 2 (re-fetch) returns the row
    execute_calls = [
        MagicMock(),  # upsert — result not used
        MagicMock(
            mappings=MagicMock(return_value=MagicMock(fetchone=MagicMock(return_value=_bot_row)))
        ),
    ]
    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute_calls)
    session.commit = AsyncMock()

    _app.dependency_overrides[bot_module.get_tenant_id] = _override_tenant_id()
    _app.dependency_overrides[bot_module.get_db] = _override_db(session)

    fake_get_me = AsyncMock(return_value={"id": 1234567890, "username": "mybot", "is_bot": True})
    try:
        with patch.object(bot_module, "_telegram_get_me", new=fake_get_me):
            resp = client.post(
                _URL,
                json={"token": _VALID_TOKEN},
                headers={"X-API-Key": "test-key"},
            )
    finally:
        _app.dependency_overrides.clear()

    assert resp.status_code == 201
    body = resp.json()
    assert body["configured"] is True
    assert body["status"] == "active"
    assert body["bot_username"] == "mybot"
    # Raw token must NEVER appear in any response field
    raw_secret = _VALID_TOKEN.split(":", 1)[1]
    assert raw_secret not in str(body)
    assert _VALID_TOKEN not in str(body)


# ---------------------------------------------------------------------------
# DELETE — configured → revoked
# ---------------------------------------------------------------------------


def test_delete_configured_returns_revoked():
    db_row = {
        "telegram_bot_token_encrypted": "ENC[123456…]",
        "telegram_bot_id": 9999,
        "telegram_bot_username": "mybot",
        "telegram_bot_status": "active",
        "telegram_validated_at": datetime.now(UTC),
        "telegram_last_active_at": None,
        "telegram_revoked_at": None,
        "telegram_last_error": None,
    }
    # execute call 1 = fetch row; call 2 = UPDATE
    execute_calls = [
        MagicMock(
            mappings=MagicMock(return_value=MagicMock(fetchone=MagicMock(return_value=db_row)))
        ),
        MagicMock(),  # UPDATE
    ]
    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute_calls)
    session.commit = AsyncMock()

    _app.dependency_overrides[bot_module.get_tenant_id] = _override_tenant_id()
    _app.dependency_overrides[bot_module.get_db] = _override_db(session)
    try:
        with patch.object(bot_module, "_telegram_delete_webhook", new=AsyncMock()):
            resp = client.delete(_URL, headers={"X-API-Key": "test-key"})
    finally:
        _app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "revoked"


# ---------------------------------------------------------------------------
# DELETE — nothing configured → still 200 revoked (idempotent)
# ---------------------------------------------------------------------------


def test_delete_not_configured_idempotent():
    db = _make_empty_db_session()
    # Second execute call for UPDATE also fine
    db.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))
        )
    )

    _app.dependency_overrides[bot_module.get_tenant_id] = _override_tenant_id()
    _app.dependency_overrides[bot_module.get_db] = _override_db(db)
    try:
        with patch.object(bot_module, "_telegram_delete_webhook", new=AsyncMock()):
            resp = client.delete(_URL, headers={"X-API-Key": "test-key"})
    finally:
        _app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"


# ---------------------------------------------------------------------------
# E3 isolation — SQL always uses the tenant_id from the API key, never a path param
# ---------------------------------------------------------------------------


def test_e3_sql_uses_api_key_tenant_not_path_param():
    """Ensure the SQL query contains the correct tenant_id.

    This test verifies that the session.execute() call receives the
    tenant_id of the authenticated tenant, not any other value injected
    by a path parameter (there are none — which is itself the E3 guarantee).
    """
    captured_params: list[dict] = []

    async def _fake_execute(stmt, params=None, **kw):
        if params:
            captured_params.append(dict(params))
        return MagicMock(
            mappings=MagicMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))
        )

    session = MagicMock()
    session.execute = _fake_execute
    session.commit = AsyncMock()

    _app.dependency_overrides[bot_module.get_tenant_id] = _override_tenant_id(_FAKE_TENANT_ID)
    _app.dependency_overrides[bot_module.get_db] = _override_db(session)
    try:
        resp = client.get(_URL, headers={"X-API-Key": "test-key"})
    finally:
        _app.dependency_overrides.clear()

    assert resp.status_code == 200
    # At least one DB call must have been made with the correct tid
    assert any(
        p.get("tid") == str(_FAKE_TENANT_ID) for p in captured_params
    ), f"Expected tid={_FAKE_TENANT_ID} in SQL params, got: {captured_params}"
    # The OTHER tenant's id must never appear
    assert not any(p.get("tid") == str(_OTHER_TENANT_ID) for p in captured_params)


# ---------------------------------------------------------------------------
# Token never in any response
# ---------------------------------------------------------------------------


def test_token_never_in_post_error_response():
    """Regression: even 400 responses must not echo back the submitted token."""
    db = _make_empty_db_session()
    _app.dependency_overrides[bot_module.get_tenant_id] = _override_tenant_id()
    _app.dependency_overrides[bot_module.get_db] = _override_db(db)
    evil_token = "9876543210:SUPERSECRETTOKEN_MUSTNOTLEAK12345"
    try:
        resp = client.post(
            _URL,
            json={"token": evil_token},
            headers={"X-API-Key": "test-key"},
        )
    finally:
        _app.dependency_overrides.clear()

    # Format is wrong by length — will hit 400
    body_text = resp.text
    assert evil_token not in body_text
    assert "SUPERSECRETTOKEN_MUSTNOTLEAK12345" not in body_text


# ---------------------------------------------------------------------------
# POST — Telegram nicht erreichbar → 503 (NICHT 400)
# ---------------------------------------------------------------------------


def test_post_netzwerkfehler_returns_503_nicht_400():
    """Ein Netzwerkfehler darf NICHT als Token-Ablehnung ausgegeben werden.

    Am 03.08.2026 scheiterte eine Bot-Registrierung an einem ReadTimeout, die API
    antwortete aber "Token von Telegram abgelehnt" (400). Derselbe Token lief
    danach unveraendert durch. Wer der Meldung glaubt, widerruft einen intakten
    Token und legt ihn neu an — ein irreversibler Schritt aufgrund einer
    Falschaussage.

    503 sagt: kein Urteil erhalten, nochmal versuchen. 400 sagt: Token ist
    kaputt. Das sind verschiedene Aussagen und duerfen nicht denselben Code teilen.
    """
    db = _make_empty_db_session()
    _app.dependency_overrides[bot_module.get_tenant_id] = _override_tenant_id()
    _app.dependency_overrides[bot_module.get_db] = _override_db(db)
    try:
        unreachable = AsyncMock(side_effect=bot_module.TelegramUnavailable("ReadTimeout"))
        with patch.object(bot_module, "_telegram_get_me", new=unreachable):
            resp = client.post(
                _URL,
                json={"token": _VALID_TOKEN},
                headers={"X-API-Key": "test-key"},
            )
    finally:
        _app.dependency_overrides.clear()

    assert resp.status_code == 503, f"erwartet 503, bekam {resp.status_code}"
    body = resp.json()
    detail = body.get("detail", "")
    assert (
        "abgelehnt" not in detail
    ), f"Meldung darf keine Token-Ablehnung behaupten — ist: {detail!r}"
    assert _VALID_TOKEN not in str(body)


def test_telegram_get_me_wirft_bei_netzwerkfehler_statt_none():
    """_telegram_get_me muss Netzwerkfehler von echter Ablehnung unterscheiden.

    Frueher gab beides None zurueck — die Information, ob ueberhaupt ein Urteil
    vorliegt, ging genau hier verloren.
    """
    import asyncio

    import httpx as _httpx
    import pytest as _pytest

    failing_client = AsyncMock()
    failing_client.__aenter__ = AsyncMock(return_value=failing_client)
    failing_client.__aexit__ = AsyncMock(return_value=False)
    failing_client.get = AsyncMock(side_effect=_httpx.ReadTimeout("timeout"))

    with patch.object(bot_module.httpx, "AsyncClient", return_value=failing_client):
        with _pytest.raises(bot_module.TelegramUnavailable):
            asyncio.run(bot_module._telegram_get_me("123456:FAKE"))


class TestInterviewAusgaenge:
    """EIN sichtbarer Weg aus einem laufenden Gespraech (Owner-Entscheid 2026-08-21)."""

    def test_frage_bietet_NUR_abbruch(self):
        """⛔ "🆕 Neuer Post" ENTFERNT — Owner 2026-08-21: "ein Klick auf
        'neuer Post', auch versehentlich, killt die ganze Arbeit bis dahin".

        Der Knopf loeste ein echtes Problem (Louis 2026-08-20 22:24: ein
        GETIPPTES "neuer Post" wurde nur als Notiz gespeichert), aber mit dem
        falschen Mittel: Er stand direkt neben "Abbrechen", war die
        destruktivere der beiden Wahlmoeglichkeiten und verwarf das laufende
        Gespraech OHNE Rueckfrage. Auf einem Telefon entscheidet dann die
        Trefferflaeche ueber ein halbes Interview.

        "Abbrechen" leistet dasselbe in zwei Schritten — beenden, dann neu
        anfangen — und der Nutzer merkt dazwischen, was passiert.

        ⛔ DIESER TEST HAELT DIE ENTSCHEIDUNG FEST: Wer den Knopf zurueckbaut,
        faellt hier auf. Der CALLBACK bleibt bestehen (s.
        test_neustart_text_meint_dasselbe_wie_der_knopf) — aeltere Nachrichten
        im Chat tragen ihn weiterhin und muessen sauber behandelt werden.
        """
        from api.telegram import _interview_cancel_keyboard

        rows = _interview_cancel_keyboard()["inline_keyboard"]
        callbacks = {b["callback_data"] for row in rows for b in row}
        assert "cmd:session_cancel" in callbacks, "Abbruch darf nicht verschwinden"
        assert "cmd:session_restart" not in callbacks, (
            "Der Neustart-Knopf ist bewusst entfernt — er vernichtet die laufende "
            "Arbeit ohne Rueckfrage (Owner 2026-08-21)"
        )
        assert sum(len(r) for r in rows) == 1, "Genau EIN Ausgang, kein Fehlklick-Risiko"

    def test_neustart_text_meint_dasselbe_wie_der_knopf(self):
        """Knopf-Wortlaut und Antwort-Wortlaut muessen dieselbe Sache meinen.

        Lehre vom 06.08.2026: Auf "🗄 Nur merken" kam "❌ Gespraech abgebrochen"
        zurueck — Louis verstand es als Absturz. Ein Knopf "🆕 Neuer Post" darf
        also keine Abbruch-Sprache antworten.
        """
        from api.telegram import _ABBRUCH_TEXT, _NEUSTART_TEXT

        assert _NEUSTART_TEXT != _ABBRUCH_TEXT
        assert "abgebrochen" not in _NEUSTART_TEXT.lower()
        assert "neuen Post" in _NEUSTART_TEXT or "neuer Post" in _NEUSTART_TEXT.lower()
