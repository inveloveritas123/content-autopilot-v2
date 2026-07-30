"""Tests für services/telegram_poller.py + tasks/telegram_poll_task.py.

Coverage:
- poll_once: Updates → next_offset=max+1
- poll_once: keine Updates → offset unverändert
- poll_once: allowed_updates korrekt gesetzt
- poll_once: offset wird gesendet wenn gesetzt, weggelassen wenn None
- poll_once: HTTP 401 → TelegramUnauthorized
- poll_once: HTTP 500 → TelegramHTTPError
- poll_once: ok=false → TelegramAPIError
- poll_all_active_bots: iteriert aktive Bots
- poll_all_active_bots: dispatcht Updates + persistiert offset
- poll_all_active_bots: fail-open bei Fehler in Bot A — Bot B läuft weiter
- poll_all_active_bots: Fehler-Bot → status='error' (TelegramUnauthorized)
- poll_all_active_bots: TELEGRAM_POLLING_ENABLED=false → skip
- Sicherheit: Token taucht in KEINEM Log-Record auf

Run:
    cd backend && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_telegram_poller.py -v

Wenn schwere Deps fehlen werden sie gestubt (identisch zum Muster in
test_telegram_outbound_pertenant.py).
"""

from __future__ import annotations

import logging
import sys
import types
import uuid
from unittest.mock import MagicMock, patch

import pytest

# ===========================================================================
# Stub-Infrastruktur (muss VOR allen Modul-Imports stehen)
# ===========================================================================


def _ensure_stub(name: str) -> types.ModuleType:
    if name not in sys.modules:
        m = types.ModuleType(name)
        sys.modules[name] = m
    return sys.modules[name]


# sqlalchemy
if "sqlalchemy" not in sys.modules:
    _sq = _ensure_stub("sqlalchemy")
    _sq.text = lambda q: q
    _sq.create_engine = MagicMock()
    _sq.select = MagicMock()
    _ensure_stub("sqlalchemy.ext")
    _sa_async = _ensure_stub("sqlalchemy.ext.asyncio")
    _sa_async.AsyncSession = MagicMock
    _sa_async.create_async_engine = MagicMock()
    _ensure_stub("sqlalchemy.orm")
    _ensure_stub("sqlalchemy.dialects")
    _ensure_stub("sqlalchemy.dialects.postgresql")

# cryptography
try:
    import cryptography.fernet as _cf_real  # noqa: F401
except ImportError:
    _c = _ensure_stub("cryptography")
    _cf = _ensure_stub("cryptography.fernet")
    _cf.Fernet = MagicMock
    _cf.InvalidToken = Exception

# config
if "config" not in sys.modules:
    _cfg = _ensure_stub("config")
    _cfg.settings = types.SimpleNamespace(
        default_tenant_key="test-key-32-bytes-padding-xxxxxxx",
        redis_url="redis://localhost:6379/1",
        database_url="postgresql+asyncpg://t:t@localhost/t",
        sync_database_url="postgresql://t:t@localhost/t",
    )

# celery
if "celery" not in sys.modules:
    _cel = _ensure_stub("celery")

    class _FakeCelery:
        def __init__(self, *a, **kw):
            self.conf = types.SimpleNamespace(
                update=lambda **kw: None,
                beat_schedule={},
                include=[],
            )

        def task(self, *a, **kw):
            def decorator(fn):
                fn.apply_async = lambda *a, **kw: None
                return fn

            if len(a) == 1 and callable(a[0]):
                fn = a[0]
                fn.apply_async = lambda *a, **kw: None
                return fn
            return decorator

    _cel.Celery = _FakeCelery
    _ensure_stub("celery.schedules").crontab = lambda *a, **kw: None

    class _FakeSig:
        def connect(self, *a, **kw):
            def d(fn):
                return fn

            return a[0] if len(a) == 1 and callable(a[0]) else d

    _sig = _ensure_stub("celery.signals")
    _sig.task_prerun = _FakeSig()
    _sig.task_postrun = _FakeSig()
    _sig.task_failure = _FakeSig()

# models.base
_ensure_stub("models")
if "models.base" not in sys.modules:
    _mb = _ensure_stub("models.base")
    _mb.sync_session_factory = MagicMock()

# services als Package stubben — verhindert Import von services/__init__.py
# der seinerseits services.llm (mit Py3.10-Union-Syntax) zieht
if "services" not in sys.modules:
    _svc_pkg = _ensure_stub("services")
    _svc_pkg.__path__ = []  # macht es zum Package

# sentry_config
_ensure_stub("sentry_config")

# datetime.UTC Py3.9-Compat
import datetime as _dt_real

if not hasattr(_dt_real, "UTC"):
    _dt_real.UTC = _dt_real.UTC  # type: ignore[attr-defined]

# services.crypto: direkt per importlib laden (dep-frei, keine __init__.py-Kette)
import importlib.util as _ilu
import os as _os

_BACKEND_DIR = _os.path.normpath(_os.path.join(_os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _load_module(dotted_name: str, rel_path: str) -> types.ModuleType:
    """Lädt ein Backend-Modul direkt per Pfad, registriert in sys.modules."""
    if dotted_name in sys.modules:
        return sys.modules[dotted_name]
    spec = _ilu.spec_from_file_location(
        dotted_name,
        _os.path.join(_BACKEND_DIR, rel_path),
    )
    mod = _ilu.module_from_spec(spec)
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod


_crypto = _load_module("services.crypto", "services/crypto.py")

# tasks-Package
if "tasks" not in sys.modules:
    _tasks_pkg = _ensure_stub("tasks")
    _tasks_pkg.__path__ = []

# tasks.celery_app laden (braucht celery-Stub — bereits oben gesetzt)
_celery_app_mod = _load_module("tasks.celery_app", "tasks/celery_app.py")

# services.telegram_poller laden
_poller_mod = _load_module("services.telegram_poller", "services/telegram_poller.py")

# api-Stubs (dispatch_inbound_update)
if "api" not in sys.modules:
    _api_pkg = _ensure_stub("api")
    _api_pkg.__path__ = []

_api_tg = _ensure_stub("api.telegram")
# NUR stubben, wenn hier wirklich ein Stub steht. _ensure_stub gibt ein bereits
# geladenes ECHTES api.telegram unverändert zurück — ein unbedingtes Überschreiben
# ersetzt dort die Produktionsfunktion DAUERHAFT (Modul-Ebene läuft beim Collect,
# ohne Teardown). Jede alphabetisch später gesammelte Testdatei bekäme dann einen
# No-Op-Mock statt dispatch_inbound_update und sähe stumme Nicht-Aufrufe.
# Die Tests, die den Dispatch beobachten, patchen ihn ohnehin lokal per
# patch.object() (:405/:446/:559) — hier muss das Attribut nur EXISTIEREN.
if not hasattr(_api_tg, "dispatch_inbound_update"):
    _api_tg.dispatch_inbound_update = MagicMock()

# services.telegram_token_resolver — eigenes Stub-Modul (NICHT _ensure_stub —
# test_telegram_outbound_pertenant lädt das echte Modul, _ensure_stub würde es
# mutieren und TestGetTenantBotToken zerstören)
_ttr = types.ModuleType("services.telegram_token_resolver")
sys.modules["services.telegram_token_resolver"] = _ttr
_ttr.get_tenant_bot_token = MagicMock(return_value="tok")
_ttr.update_last_active = MagicMock()

# tasks.telegram_poll_task laden
_poll_task_mod = _load_module("tasks.telegram_poll_task", "tasks/telegram_poll_task.py")


# ===========================================================================
# Re-Exports für Tests
# ===========================================================================

from services.telegram_poller import (
    TelegramAPIError,
    TelegramHTTPError,
    TelegramUnauthorized,
    poll_once,
)

poll_all_active_bots = _poll_task_mod.poll_all_active_bots


# ===========================================================================
# Hilfs-Konstanten und Fixtures
# ===========================================================================

_TENANT_A = str(uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"))
_TENANT_B = str(uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002"))

_TOKEN_A = "123456789:AAFakeTokenForTenantA_xxxxxxxxxxx"
_TOKEN_B = "987654321:AAFakeTokenForTenantB_xxxxxxxxxxx"


def _make_http_mock(updates: list[dict], status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"ok": True, "result": updates}
    client = MagicMock()
    client.get.return_value = resp
    return client


def _make_update(update_id: int, text: str = "hallo") -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "chat": {"id": 111111, "type": "private"},
            "text": text,
        },
    }


# ===========================================================================
# Tests: poll_once
# ===========================================================================


class TestPollOnce:
    def test_updates_returns_next_offset(self):
        """Updates kommen → next_offset = max(update_id) + 1."""
        updates = [_make_update(100), _make_update(101), _make_update(99)]
        http = _make_http_mock(updates)

        result_updates, next_offset = poll_once(_TOKEN_A, offset=None, timeout=0, http=http)

        assert len(result_updates) == 3
        assert next_offset == 102  # max(100,101,99)+1

    def test_no_updates_offset_unchanged(self):
        """Keine Updates → offset unverändert zurückgeben."""
        http = _make_http_mock([])

        result_updates, next_offset = poll_once(_TOKEN_A, offset=42, timeout=0, http=http)

        assert result_updates == []
        assert next_offset == 42

    def test_no_updates_offset_none_unchanged(self):
        """Keine Updates, kein initialer Offset → None zurück."""
        http = _make_http_mock([])

        _, next_offset = poll_once(_TOKEN_A, offset=None, timeout=0, http=http)

        assert next_offset is None

    def test_allowed_updates_in_request(self):
        """allowed_updates muss in den Request-Params enthalten sein."""
        http = _make_http_mock([])

        poll_once(_TOKEN_A, offset=None, timeout=0, http=http)

        call_kwargs = http.get.call_args
        params = call_kwargs.kwargs.get("params", {})
        assert "allowed_updates" in params
        assert "message" in params["allowed_updates"]
        assert "callback_query" in params["allowed_updates"]

    def test_offset_sent_when_set(self):
        """Wenn offset gesetzt → muss in Params übergeben werden."""
        http = _make_http_mock([])

        poll_once(_TOKEN_A, offset=77, timeout=0, http=http)

        params = http.get.call_args.kwargs.get("params", {})
        assert params.get("offset") == 77

    def test_offset_not_sent_when_none(self):
        """Wenn offset=None → kein offset-Key in Params."""
        http = _make_http_mock([])

        poll_once(_TOKEN_A, offset=None, timeout=0, http=http)

        params = http.get.call_args.kwargs.get("params", {})
        assert "offset" not in params

    def test_http_401_raises_unauthorized(self):
        """HTTP 401 → TelegramUnauthorized."""
        http = _make_http_mock([], status_code=401)

        with pytest.raises(TelegramUnauthorized):
            poll_once(_TOKEN_A, offset=None, timeout=0, http=http)

    def test_http_500_raises_http_error(self):
        """HTTP 500 → TelegramHTTPError."""
        resp = MagicMock()
        resp.status_code = 500
        http = MagicMock()
        http.get.return_value = resp

        with pytest.raises(TelegramHTTPError):
            poll_once(_TOKEN_A, offset=None, timeout=0, http=http)

    def test_ok_false_raises_api_error(self):
        """Telegram antwortet mit ok=false → TelegramAPIError."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"ok": False, "description": "Unauthorized"}
        http = MagicMock()
        http.get.return_value = resp

        with pytest.raises(TelegramAPIError):
            poll_once(_TOKEN_A, offset=None, timeout=0, http=http)

    def test_token_not_in_log(self, caplog):
        """Token darf niemals in Log-Nachrichten auftauchen (E2/D3)."""
        http = _make_http_mock([_make_update(1)])

        with caplog.at_level(logging.DEBUG, logger="services.telegram_poller"):
            poll_once(_TOKEN_A, offset=None, timeout=0, http=http)

        for record in caplog.records:
            assert (
                _TOKEN_A not in record.getMessage()
            ), f"Token in Log-Record: {record.getMessage()!r}"

    def test_single_update_next_offset(self):
        """Einzelnes Update → next_offset = update_id + 1."""
        updates = [_make_update(999)]
        http = _make_http_mock(updates)

        _, next_offset = poll_once(_TOKEN_A, offset=998, timeout=0, http=http)

        assert next_offset == 1000


# ===========================================================================
# Tests: poll_all_active_bots
# ===========================================================================


class TestPollAllActiveBots:
    def test_polls_active_bots_and_counts(self):
        """Aktive Bots werden gepollt, Zähler korrekt."""
        with (
            patch.object(
                _poll_task_mod,
                "_load_active_bots",
                return_value=[
                    {
                        "tenant_id": _TENANT_A,
                        "telegram_bot_token_encrypted": "enc_a",
                        "telegram_poll_offset": None,
                    }
                ],
            ),
            patch.object(_poll_task_mod, "decrypt_secret", return_value=_TOKEN_A),
            patch.object(_poll_task_mod, "poll_once", return_value=([], None)),
            patch.object(_poll_task_mod, "_persist_offset"),
            patch.dict("os.environ", {"TELEGRAM_POLLING_ENABLED": "true"}),
        ):
            result = poll_all_active_bots()

        assert result["bots_polled"] == 1
        assert result["updates_processed"] == 0

    def test_dispatches_updates_and_persists_offset(self):
        """Updates werden dispatcht und offset persistiert."""
        update1 = _make_update(200)
        update2 = _make_update(201)
        dispatch_mock = MagicMock()

        with (
            patch.object(
                _poll_task_mod,
                "_load_active_bots",
                return_value=[
                    {
                        "tenant_id": _TENANT_A,
                        "telegram_bot_token_encrypted": "enc_a",
                        "telegram_poll_offset": 199,
                    }
                ],
            ),
            patch.object(_poll_task_mod, "decrypt_secret", return_value=_TOKEN_A),
            patch.object(_poll_task_mod, "poll_once", return_value=([update1, update2], 202)),
            patch.object(_poll_task_mod, "_persist_offset") as mock_persist,
            patch.object(_api_tg, "dispatch_inbound_update", dispatch_mock),
            patch.dict("os.environ", {"TELEGRAM_POLLING_ENABLED": "true"}),
        ):
            result = poll_all_active_bots()

        assert result["bots_polled"] == 1
        assert result["updates_processed"] == 2
        dispatch_mock.assert_any_call(update1, _TENANT_A)
        dispatch_mock.assert_any_call(update2, _TENANT_A)
        mock_persist.assert_called_once_with(_TENANT_A, 202, last_active=True)

    def test_fail_open_one_bot_error_others_continue(self):
        """Fehler bei Bot A stoppt Bot B nicht (fail-open pro Bot)."""
        update_b = _make_update(300)
        dispatch_mock = MagicMock()

        def _poll_side(token, offset, **kw):
            if token == _TOKEN_A:
                raise TelegramHTTPError("HTTP 503 bot=...xxxxx")
            return ([update_b], 301)

        with (
            patch.object(
                _poll_task_mod,
                "_load_active_bots",
                return_value=[
                    {
                        "tenant_id": _TENANT_A,
                        "telegram_bot_token_encrypted": "enc_a",
                        "telegram_poll_offset": None,
                    },
                    {
                        "tenant_id": _TENANT_B,
                        "telegram_bot_token_encrypted": "enc_b",
                        "telegram_poll_offset": None,
                    },
                ],
            ),
            patch.object(_poll_task_mod, "decrypt_secret", side_effect=[_TOKEN_A, _TOKEN_B]),
            patch.object(_poll_task_mod, "poll_once", side_effect=_poll_side),
            patch.object(_poll_task_mod, "_persist_offset") as mock_persist,
            patch.object(_api_tg, "dispatch_inbound_update", dispatch_mock),
            patch.dict("os.environ", {"TELEGRAM_POLLING_ENABLED": "true"}),
        ):
            result = poll_all_active_bots()

        # Bot B lief trotz Fehler bei Bot A
        assert result["bots_polled"] == 1  # nur Bot B kam durch
        assert result["updates_processed"] == 1
        dispatch_mock.assert_called_once_with(update_b, _TENANT_B)
        mock_persist.assert_called_once_with(_TENANT_B, 301, last_active=True)

    def test_unauthorized_marks_bot_error(self):
        """HTTP 401 → _mark_bot_error wird aufgerufen."""
        with (
            patch.object(
                _poll_task_mod,
                "_load_active_bots",
                return_value=[
                    {
                        "tenant_id": _TENANT_A,
                        "telegram_bot_token_encrypted": "enc_a",
                        "telegram_poll_offset": None,
                    },
                ],
            ),
            patch.object(_poll_task_mod, "decrypt_secret", return_value=_TOKEN_A),
            patch.object(_poll_task_mod, "poll_once", side_effect=TelegramUnauthorized("401")),
            patch.object(_poll_task_mod, "_mark_bot_error") as mock_mark,
            patch.dict("os.environ", {"TELEGRAM_POLLING_ENABLED": "true"}),
        ):
            result = poll_all_active_bots()

        mock_mark.assert_called_once_with(_TENANT_A, "token_rejected_401")
        assert result["bots_polled"] == 0

    def test_empty_token_after_decrypt_skipped(self):
        """Leeres Token nach Decrypt → Bot überspringen, kein poll_once."""
        with (
            patch.object(
                _poll_task_mod,
                "_load_active_bots",
                return_value=[
                    {
                        "tenant_id": _TENANT_A,
                        "telegram_bot_token_encrypted": "enc_a",
                        "telegram_poll_offset": None,
                    },
                ],
            ),
            patch.object(_poll_task_mod, "decrypt_secret", return_value=""),
            patch.object(_poll_task_mod, "poll_once") as mock_poll,
            patch.dict("os.environ", {"TELEGRAM_POLLING_ENABLED": "true"}),
        ):
            result = poll_all_active_bots()

        mock_poll.assert_not_called()
        assert result["bots_polled"] == 0

    def test_polling_disabled_env_skips_db(self):
        """TELEGRAM_POLLING_ENABLED=false → kein DB-Zugriff, sofortiger Return."""
        with (
            patch.object(_poll_task_mod, "_load_active_bots") as mock_load,
            patch.dict("os.environ", {"TELEGRAM_POLLING_ENABLED": "false"}),
        ):
            result = poll_all_active_bots()

        mock_load.assert_not_called()
        assert result.get("skipped") is True

    def test_token_not_in_any_log_output(self, caplog):
        """Token darf in KEINER Log-Nachricht auftauchen (D3/E2)."""
        with (
            patch.object(
                _poll_task_mod,
                "_load_active_bots",
                return_value=[
                    {
                        "tenant_id": _TENANT_A,
                        "telegram_bot_token_encrypted": "enc_a",
                        "telegram_poll_offset": None,
                    },
                ],
            ),
            patch.object(_poll_task_mod, "decrypt_secret", return_value=_TOKEN_A),
            patch.object(_poll_task_mod, "poll_once", side_effect=TelegramUnauthorized("401")),
            patch.object(_poll_task_mod, "_mark_bot_error", return_value=None),
            patch.dict("os.environ", {"TELEGRAM_POLLING_ENABLED": "true"}),
        ):
            with caplog.at_level(logging.DEBUG):
                poll_all_active_bots()

        for record in caplog.records:
            msg = record.getMessage()
            assert _TOKEN_A not in msg, f"Token A in Log: {msg!r}"
            assert _TOKEN_B not in msg, f"Token B in Log: {msg!r}"

    def test_returns_summary_no_pii_keys(self):
        """Rückgabe enthält nur erlaubte Schlüssel (keine Tokens, keine tenant_ids)."""
        with (
            patch.object(
                _poll_task_mod,
                "_load_active_bots",
                return_value=[
                    {
                        "tenant_id": _TENANT_A,
                        "telegram_bot_token_encrypted": "enc_a",
                        "telegram_poll_offset": 10,
                    },
                ],
            ),
            patch.object(_poll_task_mod, "decrypt_secret", return_value=_TOKEN_A),
            patch.object(_poll_task_mod, "poll_once", return_value=([_make_update(11)], 12)),
            patch.object(_poll_task_mod, "_persist_offset"),
            patch.object(_api_tg, "dispatch_inbound_update", MagicMock()),
            patch.dict("os.environ", {"TELEGRAM_POLLING_ENABLED": "true"}),
        ):
            result = poll_all_active_bots()

        allowed_keys = {"bots_polled", "updates_processed"}
        for key in result:
            assert key in allowed_keys, f"Unerwarteter Key: {key!r}"
        # Kein Token im repr
        assert _TOKEN_A not in str(result)
