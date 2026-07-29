"""Tests für per-Tenant Telegram-Outbound-Routing.

Prüft:
- resolver gibt Token / None zurück
- _send_telegram_message ohne aktiven Bot → skip (kein Send)
- _send_telegram_message mit Bot → Send + last_active_at-Update
- Token wird NIEMALS geloggt (E2/D3)
- _send_admin_telegram_message nutzt globalen Token (kein Tenant-Lookup)

Alle DB- und HTTP-Calls sind per Mock ersetzt — keine echte DB / kein echtes Netz.
Lokaler Py3.9-venv ohne sqlalchemy → Stub-Strategie wie _telegram_task_env.py.

Run:
    cd backend && PYTHONPATH=. ../../.venv/bin/python -m pytest \\
        tests/test_telegram_outbound_pertenant.py -v
"""

from __future__ import annotations

import logging
import sys
import types
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub-Basisumgebung (identisch zum Muster in _telegram_task_env.py)
# ---------------------------------------------------------------------------


def _ensure_stub(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# sqlalchemy-Stubs (nur wenn sqlalchemy wirklich nicht installiert ist)
try:
    import sqlalchemy  # noqa: F401
except ImportError:
    _sq = _ensure_stub("sqlalchemy")
    _sq.text = lambda q: q
    _sq.create_engine = MagicMock()
    _ensure_stub("sqlalchemy.ext")
    _ensure_stub("sqlalchemy.ext.asyncio")
    _ensure_stub("sqlalchemy.orm")

# cryptography-Stub (Fernet — nur wenn echte Bibliothek nicht installierbar ist)
# Wichtig: NUR stubben wenn cryptography wirklich fehlt — andernfalls test_crypto.py
# bekommt einen nicht-deterministischen Fake der seine Tests kaputtmacht.
try:
    import cryptography.fernet as _cf_real  # type: ignore[import]  # noqa: F401
    # Echte cryptography verfügbar — kein Stub nötig
except ImportError:
    _c = _ensure_stub("cryptography")
    _cf = _ensure_stub("cryptography.fernet")

    class _FakeFernet:
        """Fernet-Stub der Schlüssel korrekt einbezieht (salt-isolation simulieren)."""

        def __init__(self, key: bytes):
            self._key = key

        def encrypt(self, data: bytes) -> bytes:
            # Schlüssel in Ciphertext einbetten damit different-key → different-ciphertext
            return b"ENCRYPTED[" + self._key + b"]:" + data

        def decrypt(self, token: bytes) -> bytes:
            prefix = b"ENCRYPTED[" + self._key + b"]:"
            if token.startswith(prefix):
                return token[len(prefix) :]
            # Falscher Schlüssel → InvalidToken
            raise _InvalidToken("wrong key")

    class _InvalidToken(Exception):
        pass

    _cf.Fernet = _FakeFernet
    _cf.InvalidToken = _InvalidToken

# config-Stub
_created_config_stub = False
if "config" not in sys.modules:
    _created_config_stub = True
    _cfg = _ensure_stub("config")
    _cfg.settings = types.SimpleNamespace(
        telegram_bot_token="GLOBAL_ADMIN_TOKEN",
        telegram_admin_chat_id="99999",
        default_tenant_key="test-key-32-chars-padded-xxxxxxxx",
        database_url="postgresql+asyncpg://t:t@localhost/t",
        sync_database_url="postgresql://t:t@localhost/t",
        # Required by services/__init__.py → LLMService() and NextcloudClient()
        litellm_base_url="https://stub-requesty/v1",
        litellm_api_key="stub-key",
        nextcloud_url="https://stub-nextcloud",
        nextcloud_user="stub",
        nextcloud_password="stub",
    )

# models.base-Stub (nur wenn models noch nicht real geladen)
if "models" not in sys.modules:
    _ensure_stub("models")
    if "models.base" not in sys.modules:
        _mb = _ensure_stub("models.base")
        _mb.sync_session_factory = MagicMock()
    # services.provider_resolver imports models.llm_provider — stub it to prevent ImportError
    if "models.llm_provider" not in sys.modules:
        _ensure_stub("models.llm_provider").LLMProvider = MagicMock

# datetime.UTC Py3.9-Compat-Stub:
# api/telegram.py importiert `from datetime import UTC` — erst ab Py3.11.
# Nur das Modul mutieren, NICHT sys.modules["datetime"] ersetzen
# (Ersatz bricht FastAPI's class-Identity durch Doppelimport).
import datetime as _dt_real

if not hasattr(_dt_real, "UTC"):
    _dt_real.UTC = _dt_real.UTC  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Modul unter Test laden: services.telegram_token_resolver
# ---------------------------------------------------------------------------

import importlib.util as _ilu
import os

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# services.crypto importieren (dep-frei genug mit Fernet-Stub)
_crypto_spec = _ilu.spec_from_file_location(
    "services.crypto",
    os.path.join(_BACKEND_DIR, "services", "crypto.py"),
)
_crypto_mod = _ilu.module_from_spec(_crypto_spec)
sys.modules["services.crypto"] = _crypto_mod
_crypto_spec.loader.exec_module(_crypto_mod)

# services.telegram_token_resolver
_ttr_spec = _ilu.spec_from_file_location(
    "services.telegram_token_resolver",
    os.path.join(_BACKEND_DIR, "services", "telegram_token_resolver.py"),
)
_ttr_mod = _ilu.module_from_spec(_ttr_spec)
sys.modules["services.telegram_token_resolver"] = _ttr_mod
_ttr_spec.loader.exec_module(_ttr_mod)

# api.telegram laden — mit vorgeladenen Stubs für schwere Deps
_ensure_stub("api")
_at_stub = _ensure_stub("api.telegram")  # Platzhalter; wird gleich überschrieben

# Stubs für api.telegram-Deps (nur wenn nicht installierbar)
try:
    import services.embedding_service  # noqa: F401
except (ImportError, Exception):
    _es = _ensure_stub("services.embedding_service")
    _es.search_similar = MagicMock()
    _es.store_chunk = MagicMock()
# asyncpg / sqlalchemy.ext.asyncio benötigt keine vollständigen Stubs hier —
# api.telegram importiert sie lazy (nur in _memory_search_sync/_memory_note_sync).
# Für die Tests dieser Datei werden diese Pfade nicht aufgerufen.
# Aber wir brauchen sqlalchemy.orm.sessionmaker in Stubs:
if not hasattr(sys.modules.get("sqlalchemy.orm", types.ModuleType("x")), "sessionmaker"):
    _sq_orm = _ensure_stub("sqlalchemy.orm")
    _sq_orm.sessionmaker = MagicMock()

_at_spec = _ilu.spec_from_file_location(
    "api.telegram",
    os.path.join(_BACKEND_DIR, "api", "telegram.py"),
)
_at_mod = _ilu.module_from_spec(_at_spec)
sys.modules["api.telegram"] = _at_mod
_at_spec.loader.exec_module(_at_mod)

# Referenzen für Tests
resolver = _ttr_mod
tg = _at_mod

# Restore config isolation: the SimpleNamespace stub above only needed to satisfy
# `from config import settings` while exec'ing api/telegram.py and the service
# modules loaded above (they've bound their references now). Leaving it in
# sys.modules leaks a settings object missing most fields into later-collected
# modules — e.g. test_telegram_bot_api is fixed to clean up too, and
# test_throttle_adversarial patches config.settings.max_calls_per_tenant_per_hour,
# which this stub lacks. Drop it so downstream re-imports the real config.
if _created_config_stub:
    sys.modules.pop("config", None)


# ---------------------------------------------------------------------------
# Helper: Mock-DB-Session-Context-Manager
# ---------------------------------------------------------------------------


def _make_db_mock(row=None) -> MagicMock:
    """Erzeugt einen Mock-Session-Context-Manager.

    row=None     → fetchone() gibt None zurück (kein Token)
    row=(val,)   → fetchone() gibt das Tupel zurück
    """
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    db.execute.return_value.fetchone.return_value = row
    return db


# ===========================================================================
# Tests: resolver
# ===========================================================================


class TestGetTenantBotToken:
    """services.telegram_token_resolver.get_tenant_bot_token"""

    def test_returns_none_when_no_row(self):
        """Kein DB-Eintrag → None."""
        db_mock = _make_db_mock(row=None)
        with patch.object(resolver, "sync_session_factory", return_value=db_mock):
            result = resolver.get_tenant_bot_token("tenant-123")
        assert result is None

    def test_returns_none_for_empty_tenant_id(self):
        """Leere tenant_id → sofort None, kein DB-Call."""
        result = resolver.get_tenant_bot_token("")
        assert result is None

    def test_returns_none_when_encrypted_empty(self):
        """Row vorhanden aber encrypted-Feld leer → None."""
        db_mock = _make_db_mock(row=("",))
        with patch.object(resolver, "sync_session_factory", return_value=db_mock):
            result = resolver.get_tenant_bot_token("tenant-123")
        assert result is None

    def test_decrypts_token_correctly(self):
        """Gültig verschlüsselter Token → entschlüsselt zurückgegeben."""
        # Encrypt a token using the same salt
        raw_token = "123456:ABCdef_test_token"
        encrypted = _crypto_mod.encrypt_secret(raw_token, salt="-telegram-encrypt")

        db_mock = _make_db_mock(row=(encrypted,))
        with patch.object(resolver, "sync_session_factory", return_value=db_mock):
            result = resolver.get_tenant_bot_token("tenant-123")
        assert result == raw_token

    def test_returns_none_on_db_error(self):
        """DB-Fehler → None (fail-safe), kein Raise."""
        db_mock = MagicMock()
        db_mock.__enter__ = MagicMock(side_effect=Exception("DB down"))
        with patch.object(resolver, "sync_session_factory", return_value=db_mock):
            result = resolver.get_tenant_bot_token("tenant-123")
        assert result is None

    def test_token_never_in_log(self, caplog):
        """Token darf NICHT in Log-Ausgaben erscheinen (E2/D3)."""
        raw_token = "7890:SECRET_BOT_TOKEN"
        encrypted = _crypto_mod.encrypt_secret(raw_token, salt="-telegram-encrypt")

        db_mock = _make_db_mock(row=(encrypted,))
        with (
            patch.object(resolver, "sync_session_factory", return_value=db_mock),
            caplog.at_level(logging.DEBUG),
        ):
            resolver.get_tenant_bot_token("tenant-123")

        for record in caplog.records:
            assert (
                raw_token not in record.getMessage()
            ), f"Token im Log gefunden: {record.getMessage()}"


# ===========================================================================
# Tests: _send_telegram_message (per-tenant)
# ===========================================================================


class TestSendTelegramMessagePerTenant:
    """api.telegram._send_telegram_message mit tenant_id"""

    def test_skip_when_no_active_bot(self):
        """Kein aktiver Bot → kein HTTP-Call, return False."""
        with (
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "get_tenant_bot_token",
                return_value=None,
            ),
            patch("httpx.post") as mock_post,
        ):
            result = tg._send_telegram_message(12345, "Hello", tenant_id="tenant-abc")

        assert result is False
        mock_post.assert_not_called()

    def test_sends_when_bot_active(self):
        """Aktiver Bot → HTTP POST an Telegram-API."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "get_tenant_bot_token",
                return_value="987654:TENANT_TOKEN",
            ),
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "update_last_active",
            ) as mock_update,
            patch("httpx.post", return_value=mock_response) as mock_post,
        ):
            result = tg._send_telegram_message(12345, "Test msg", tenant_id="tenant-abc")

        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        # URL enthält Token (muss nicht in Log aber darf in URL sein)
        url = call_kwargs[0][0]
        assert "987654:TENANT_TOKEN" in url
        assert "sendMessage" in url
        # Payload
        body = call_kwargs[1]["json"]
        assert body["chat_id"] == 12345
        assert body["text"] == "Test msg"
        # last_active_at aktualisiert
        mock_update.assert_called_once_with("tenant-abc")

    def test_updates_last_active_on_success(self):
        """Erfolgreich gesendet → update_last_active wird aufgerufen."""
        with (
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "get_tenant_bot_token",
                return_value="111:TOKEN",
            ),
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "update_last_active",
            ) as mock_update,
            patch("httpx.post"),
        ):
            tg._send_telegram_message(99, "msg", tenant_id="t-xyz")

        mock_update.assert_called_once_with("t-xyz")

    def test_no_send_no_last_active_when_no_token(self):
        """Kein Token → update_last_active wird NICHT aufgerufen."""
        with (
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "get_tenant_bot_token",
                return_value=None,
            ),
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "update_last_active",
            ) as mock_update,
            patch("httpx.post") as mock_post,
        ):
            tg._send_telegram_message(99, "msg", tenant_id="t-xyz")

        mock_post.assert_not_called()
        mock_update.assert_not_called()

    def test_token_never_in_log(self, caplog):
        """Token darf NICHT in Log-Ausgaben erscheinen (E2/D3)."""
        secret_token = "555555:NEVER_LOG_ME"
        with (
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "get_tenant_bot_token",
                return_value=secret_token,
            ),
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "update_last_active",
            ),
            patch("httpx.post"),
            caplog.at_level(logging.DEBUG),
        ):
            tg._send_telegram_message(12345, "Safe message", tenant_id="t-test")

        for record in caplog.records:
            assert secret_token not in record.getMessage(), f"Token im Log: {record.getMessage()}"

    def test_fail_open_on_http_error(self):
        """HTTP-Fehler → return False, kein Raise (fail-open)."""
        import httpx

        with (
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "get_tenant_bot_token",
                return_value="111:TOKEN",
            ),
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "update_last_active",
            ),
            patch("httpx.post", side_effect=httpx.RequestError("timeout", request=MagicMock())),
        ):
            result = tg._send_telegram_message(99, "msg", tenant_id="t-err")

        assert result is False

    def test_logs_outbound_row_on_success(self):
        """Erfolgreicher Send → telegram_message_log-Zeile (direction='out', send_status='sent').

        Instrumentierungs-Lücke aus #119: erfolgreiche Sends waren unsichtbar, weil
        NUR der Fehlerzweig eine 'out'-Zeile schrieb. Der DoD-Marker
        „erster echter direction='out'" braucht die Erfolgs-Zeile.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        db_mock = _make_db_mock()

        with (
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "get_tenant_bot_token",
                return_value="987654:TENANT_TOKEN",
            ),
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "update_last_active",
            ),
            patch.object(tg, "sync_session_factory", return_value=db_mock),
            patch("httpx.post", return_value=mock_response),
        ):
            result = tg._send_telegram_message(12345, "Test msg", tenant_id="tenant-abc")

        assert result is True
        insert_calls = [
            c
            for c in db_mock.execute.call_args_list
            if "INSERT INTO telegram_message_log" in str(c.args[0])
        ]
        assert len(insert_calls) == 1, "erwartet: genau ein Outbound-Log-INSERT bei Erfolg"
        sql = str(insert_calls[0].args[0])
        assert "'out'" in sql
        payload = insert_calls[0].args[1]["payload"]
        assert '"send_status": "sent"' in payload


# ===========================================================================
# Tests: _send_admin_telegram_message
# ===========================================================================


class TestSendAdminTelegramMessage:
    """api.telegram._send_admin_telegram_message — nutzt globalen Token."""

    def test_uses_global_token(self):
        """Admin-Alert nutzt settings.telegram_bot_token, NICHT den Tenant-Token."""
        # Fake settings mit globalem Admin-Token
        fake_settings = types.SimpleNamespace(
            telegram_bot_token="GLOBAL_TOKEN",
        )
        tg.settings = fake_settings

        with patch("httpx.post") as mock_post:
            tg._send_admin_telegram_message(88888, "Admin alert")

        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        assert "GLOBAL_TOKEN" in url
        assert "sendMessage" in url

    def test_skip_when_no_global_token(self):
        """Kein globaler Token konfiguriert → kein HTTP-Call."""
        fake_settings = types.SimpleNamespace(telegram_bot_token=None)
        tg.settings = fake_settings

        with patch("httpx.post") as mock_post:
            tg._send_admin_telegram_message(88888, "Admin alert")

        mock_post.assert_not_called()

    def test_no_tenant_lookup(self):
        """Admin-Alert ruft get_tenant_bot_token NICHT auf."""
        fake_settings = types.SimpleNamespace(telegram_bot_token="GLOBAL_TOKEN")
        tg.settings = fake_settings

        with (
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "get_tenant_bot_token",
            ) as mock_resolver,
            patch("httpx.post"),
        ):
            tg._send_admin_telegram_message(88888, "msg")

        mock_resolver.assert_not_called()
