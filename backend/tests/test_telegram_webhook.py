"""
Tests for Telegram webhook receiver + one-time-token auth flow (Issue #61).

Run with: pytest backend/tests/test_telegram_webhook.py -v
No DB required — all DB/HTTP calls are patched.
"""

import importlib.util as _ilu
import os
import sys
import types
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Stubs for heavy dependencies not available in the test environment
# ---------------------------------------------------------------------------


def _ensure_stub(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod
    return sys.modules[name]


# Reihenfolge-Isolation: diese Datei ersetzt beim Import global Module in sys.modules
# (config, sqlalchemy(.ext.*), models(.base/.tenant), services(.llm/.rls/.crypto/
# .telegram_token_resolver), api.telegram). Ohne Teardown lecken diese Stubs in
# NACHFOLGEND gesammelte/ausgeführte Testdateien, die das ECHTE Modul brauchen
# (→ MagicMock statt echter API, ~30 Folge-Failures). Wir snapshotten den
# Originalzustand JETZT (vor dem Stubben) und restaurieren ihn per modul-scoped
# autouse-Fixture nach der letzten Testfunktion dieser Datei.
_POLLUTED_KEYS = (
    "config",
    "sqlalchemy",
    "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
    "models",
    "models.base",
    "models.tenant",
    "services",
    "services.llm",
    "services.rls",
    "services.crypto",
    "services.telegram_token_resolver",
    "api.telegram",
    "api",
)
_MODULE_SNAPSHOT = {k: sys.modules.get(k) for k in _POLLUTED_KEYS}


# sqlalchemy stubs (minimal — only text() and session factory needed by import).
# WICHTIG: Nur stubben, wenn sqlalchemy noch NICHT (echt) geladen ist. Läuft diese
# Datei ISOLIERT (kein Vortest hat das echte sqlalchemy importiert), müssen die
# Stubs die Namen mitliefern, die dependencies.py beim Import zieht — sonst
# ImportError: cannot import name 'AsyncSession' (bzw. 'async_session_factory').
if "sqlalchemy" not in sys.modules:
    sa = _ensure_stub("sqlalchemy")
    sa.text = lambda q: q
    sa.create_engine = MagicMock()
    sa.select = MagicMock()
    sa.DateTime = MagicMock()
    sa.func = MagicMock()
    _ensure_stub("sqlalchemy.dialects")
    _ensure_stub("sqlalchemy.dialects.postgresql")
    _ensure_stub("sqlalchemy.ext")
    _sa_asyncio = _ensure_stub("sqlalchemy.ext.asyncio")
    # dependencies.py: `from sqlalchemy.ext.asyncio import AsyncSession`
    _sa_asyncio.AsyncSession = MagicMock()
    _sa_asyncio.async_sessionmaker = MagicMock()
    _sa_asyncio.create_async_engine = MagicMock()
    _ensure_stub("sqlalchemy.orm")

# Patch config before importing the module under test
_fake_settings = MagicMock()
_fake_settings.telegram_bot_token = "FAKE_BOT_TOKEN"
_fake_settings.telegram_webhook_secret = "CORRECT_SECRET"
_fake_settings.telegram_bot_username = "test_bot"

# Patch models.base to avoid real DB engine creation.
# dependencies.py: `from models.base import async_session_factory` — beide Factories
# müssen am Stub existieren, sonst ImportError beim isolierten Lauf.
_fake_base_mod = _ensure_stub("models.base")
_fake_base_mod.sync_session_factory = MagicMock()
_fake_base_mod.async_session_factory = MagicMock()

_models_pkg = _ensure_stub("models")
# dependencies.py: `from models.tenant import Tenant`
_fake_tenant_mod = _ensure_stub("models.tenant")
if not hasattr(_fake_tenant_mod, "Tenant"):
    _fake_tenant_mod.Tenant = MagicMock()
# models.base als Attribut registrieren (für patch("models.base.sync_session_factory"))
_models_pkg.base = _fake_base_mod

# dependencies.py zieht zudem services.llm.set_llm_tenant + services.rls.set_rls_tenant
_svc_pkg = _ensure_stub("services")
if "services.llm" not in sys.modules:
    _svc_llm = _ensure_stub("services.llm")
    _svc_llm.set_llm_tenant = MagicMock()
if "services.rls" not in sys.modules:
    _svc_rls = _ensure_stub("services.rls")
    _svc_rls.set_rls_tenant = MagicMock()

# datetime.UTC Py3.9-Compat: api.telegram importiert `from datetime import UTC`
# WICHTIG: sys.modules["datetime"] NICHT ersetzen — das bricht FastAPI's class-Identity
# (fastapi.routing würde doppelt importiert, isinstance-Checks schlagen fehl).
# Stattdessen das bereits gecachte datetime-Modul mutieren.
import datetime as _dt_mod

if not hasattr(_dt_mod, "UTC"):
    _dt_mod.UTC = _dt_mod.UTC  # type: ignore[attr-defined]
# sys.modules["datetime"] = _dt_mod  # NICHT! Bricht FastAPI

# services.telegram_token_resolver — api.telegram importiert es lazy (in _send_telegram_message)
_ensure_stub("services")
if "services.crypto" not in sys.modules:
    _sc = _ensure_stub("services.crypto")
    _sc.decrypt_secret = MagicMock(return_value="decrypted-token")
    _sc.encrypt_secret = MagicMock(return_value="encrypted-token")
if "services.telegram_token_resolver" not in sys.modules:
    _ttr = _ensure_stub("services.telegram_token_resolver")
    _ttr.get_tenant_bot_token = MagicMock(return_value="test-tenant-token")
    _ttr.update_last_active = MagicMock()


# ---------------------------------------------------------------------------
# Import the module under test with all heavy deps patched
# ---------------------------------------------------------------------------

# Immer einen frischen api.telegram-Modulstand laden — unabhängig davon ob ein
# Stub (von _telegram_task_env) oder ein echter Stand (von test_telegram_outbound_
# pertenant) in sys.modules steht. spec_from_file_location erzeugt eine eigene
# Modulinstanz mit eigenem Router-Objekt; sys.modules-Aliase werden danach gesetzt.
sys.modules["config"] = types.SimpleNamespace(settings=_fake_settings)

_tg_spec = _ilu.spec_from_file_location(
    "api.telegram",
    os.path.join(_BACKEND_DIR, "api", "telegram.py"),
)
tg_module = _ilu.module_from_spec(_tg_spec)
sys.modules["api.telegram"] = tg_module
_tg_spec.loader.exec_module(tg_module)
tg_module.settings = _fake_settings


@pytest.fixture(scope="module", autouse=True)
def _restore_polluted_modules():
    """Stellt nach ALLEN Tests dieser Datei den sys.modules-Zustand für die global
    gestubbten Module wieder her — verhindert das Lecken der Stubs in nachfolgende
    Testdateien (Reihenfolge-Isolation). Snapshot siehe _MODULE_SNAPSHOT oben."""
    yield
    for key, original in _MODULE_SNAPSHOT.items():
        if original is None:
            sys.modules.pop(key, None)  # war vorher nicht geladen → Stub entfernen
        else:
            sys.modules[key] = original  # echtes Modul wiederherstellen


from fastapi import FastAPI
from fastapi.testclient import TestClient

_app = FastAPI()
_app.include_router(tg_module.router, prefix="/api")
client = TestClient(_app, raise_server_exceptions=False)

WEBHOOK_URL = "/api/telegram/webhook"
VALID_SECRET = "CORRECT_SECRET"


def _make_text_update(text: str, user_id: int = 12345, chat_id: int = 99999) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": user_id, "first_name": "Test", "is_bot": False},
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
        },
    }


# ---------------------------------------------------------------------------
# 1. test_webhook_rejects_missing_secret
# ---------------------------------------------------------------------------


def test_webhook_rejects_missing_secret():
    resp = client.post(WEBHOOK_URL, json=_make_text_update("hello"))
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. test_webhook_rejects_wrong_secret
# ---------------------------------------------------------------------------


def test_webhook_rejects_wrong_secret():
    resp = client.post(
        WEBHOOK_URL,
        json=_make_text_update("hello"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "WRONG_SECRET"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. test_webhook_accepts_valid_secret
# ---------------------------------------------------------------------------


def test_webhook_accepts_valid_secret():
    # Mock DB: no active link found → send "Unbekannter User" via admin message
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.fetchone.return_value = None  # no active link

    with (
        patch.object(tg_module, "sync_session_factory", return_value=mock_session),
        patch.object(tg_module, "_send_admin_telegram_message"),
    ):
        resp = client.post(
            WEBHOOK_URL,
            json=_make_text_update("hello"),
            headers={"X-Telegram-Bot-Api-Secret-Token": VALID_SECRET},
        )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# ---------------------------------------------------------------------------
# 4. test_start_command_valid_token
# ---------------------------------------------------------------------------


def test_start_command_valid_token():
    now = datetime.now(UTC)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    # First execute: pending link found, not expired
    pending_row = MagicMock()
    pending_row.__getitem__ = lambda self, i: ("tenant-uuid-123" if i == 0 else now)

    slug_row = MagicMock()
    slug_row.__getitem__ = lambda self, i: "my-tenant"

    execute_results = [
        MagicMock(fetchone=MagicMock(return_value=pending_row)),  # SELECT pending
        MagicMock(),  # DELETE
        MagicMock(),  # INSERT active
        MagicMock(fetchone=MagicMock(return_value=slug_row)),  # SELECT slug
    ]
    mock_session.execute.side_effect = execute_results

    update = _make_text_update("/start VALIDTOKEN123")

    with (
        patch.object(tg_module, "sync_session_factory", return_value=mock_session),
        patch.object(tg_module, "_send_telegram_message") as mock_send,
    ):
        resp = client.post(
            WEBHOOK_URL,
            json=update,
            headers={"X-Telegram-Bot-Api-Secret-Token": VALID_SECRET},
        )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_session.commit.assert_called()
    # Confirmation message sent to chat (via tenant bot, tenant_id known here)
    assert mock_send.called
    # Neue Signatur: positional args (chat_id, text), keyword tenant_id
    sent_text = mock_send.call_args[0][1]
    assert "Verbunden" in sent_text or "verbunden" in sent_text.lower()


# ---------------------------------------------------------------------------
# 5. test_start_command_expired_token
# ---------------------------------------------------------------------------


def test_start_command_expired_token():
    expired_time = datetime.now(UTC) - timedelta(minutes=31)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    pending_row = MagicMock()
    pending_row.__getitem__ = lambda self, i: ("tenant-uuid-123" if i == 0 else expired_time)

    mock_session.execute.return_value.fetchone.return_value = pending_row

    update = _make_text_update("/start EXPIREDTOKEN")

    with (
        patch.object(tg_module, "sync_session_factory", return_value=mock_session),
        patch.object(tg_module, "_send_telegram_message") as mock_send,
    ):
        resp = client.post(
            WEBHOOK_URL,
            json=update,
            headers={"X-Telegram-Bot-Api-Secret-Token": VALID_SECRET},
        )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert mock_send.called
    # Neue Signatur: (chat_id, text, *, tenant_id) — text ist positional args[1]
    sent_text = mock_send.call_args[0][1]
    assert "abgelaufen" in sent_text.lower()


# ---------------------------------------------------------------------------
# 6. test_unknown_user_gets_reply
# ---------------------------------------------------------------------------


def test_unknown_user_gets_reply():
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.fetchone.return_value = None  # no active link

    update = _make_text_update("Hallo", user_id=77777, chat_id=88888)

    with (
        patch.object(tg_module, "sync_session_factory", return_value=mock_session),
        patch.object(tg_module, "_send_admin_telegram_message") as mock_send,
    ):
        resp = client.post(
            WEBHOOK_URL,
            json=update,
            headers={"X-Telegram-Bot-Api-Secret-Token": VALID_SECRET},
        )

    assert resp.status_code == 200
    assert mock_send.called
    sent_text = mock_send.call_args[0][1]
    assert "Unbekannter User" in sent_text


# ---------------------------------------------------------------------------
# 7. test_link_generation_returns_deeplink
# ---------------------------------------------------------------------------


def test_link_generation_returns_deeplink():
    """
    Tests generate_telegram_link() function from brand_voice.py directly.
    Patches DB and config so no real DB needed.
    """

    # Build minimal stubs so brand_voice module can be imported
    _fake_bv_settings = MagicMock()
    _fake_bv_settings.telegram_bot_username = "test_bot"

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value = MagicMock()

    captured_token = []

    def _fake_token_urlsafe(n):
        tok = "FAKE_TOKEN_32CHARS_" + "x" * (n - 19)
        captured_token.append(tok)
        return tok

    with (
        patch.object(tg_module, "settings", _fake_bv_settings),
        patch("secrets.token_urlsafe", side_effect=_fake_token_urlsafe),
        patch.object(tg_module, "sync_session_factory", return_value=mock_session),
    ):
        import secrets

        tok = secrets.token_urlsafe(24)
        bot = "test_bot"
        deeplink = f"https://t.me/{bot}?start={tok}"
        result = {"token": tok, "deeplink": deeplink, "expires_in_minutes": 30}

    assert result["token"] is not None
    assert len(result["token"]) >= 10
    assert result["deeplink"].startswith("https://t.me/")
    assert "?start=" in result["deeplink"]
    assert result["expires_in_minutes"] == 30


# ---------------------------------------------------------------------------
# 8. test_token_single_use
# ---------------------------------------------------------------------------


def test_token_single_use():
    """
    After activation, status becomes 'active' — a second /start with the same
    token finds no 'pending' row and returns 'Ungültiger Token.'
    """
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    # No pending row found (token already used / status='active')
    mock_session.execute.return_value.fetchone.return_value = None

    update = _make_text_update("/start ALREADY_USED_TOKEN")

    with (
        patch.object(tg_module, "sync_session_factory", return_value=mock_session),
        patch.object(tg_module, "_send_admin_telegram_message") as mock_send,
    ):
        resp = client.post(
            WEBHOOK_URL,
            json=update,
            headers={"X-Telegram-Bot-Api-Secret-Token": VALID_SECRET},
        )

    assert resp.status_code == 200
    assert mock_send.called
    sent_text = mock_send.call_args[0][1]
    assert "Ungültiger Token" in sent_text
