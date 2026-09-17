# AUDITED-2026-09-17 (zubu-telegram-tests-isoliert-rot) — vollstaendig gelesen
# AUDITED-2026-09-17 (zubu-stub-klasse) — vollstaendig gelesen, Package-Attribut
# fuer telegram_token_resolver ergaenzt + _ensure_package __path__-Bug behoben
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

import pytest

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

# models-Stub — DETERMINISTISCH statt fragiler "if not in sys.modules"-Guards.
#
# Hintergrund (2026-07-21, Suite-Kontext-Crash): Andere Testdateien (z.B.
# test_telegram_bot_api.py) stubben "models" via `types.ModuleType("models")`
# OHNE __path__ zu setzen und lassen den Stub nach ihrem Lauf in sys.modules
# zurück. tests/conftest.py::pytest_collectstart setzt zwar `models.base` und
# `models.tenant` vor jeder neuen Testdatei-Collection zurück, NICHT aber das
# bloße "models"-Package selbst (bewusst eng gehalten, siehe conftest.py).
# Ergebnis: `sys.modules["models"]` kann beim Collection-Start dieser Datei
# ein bereits vorhandener, aber kaputter (kein __path__) Nicht-Package-Stub
# sein → ein reines "if 'models' not in sys.modules"-Guard greift dann NICHT
# und `from models.base import ...` crasht mit "'models' is not a package".
#
# Fix: __path__ IMMER sicherstellen (idempotent — echte Packages haben schon
# ein gültiges __path__, das bleibt unangetastet), und die von uns benötigten
# Attribute auf models.base / models.tenant IMMER vorhanden machen (additiv:
# ein bereits reales, funktionierendes Modul wird nicht überschrieben, nur um
# fehlende Attribute ergänzt — andere, evtl. noch laufende Tests, die auf ein
# echtes models.base angewiesen sind, werden dadurch nicht zerstört).


def _ensure_package(name: str) -> types.ModuleType:
    """Wie _ensure_stub, garantiert aber zusätzlich ein gültiges __path__.

    Robust gegen Pollution aus anderen Testdateien: auch wenn `name` bereits
    in sys.modules steht (z.B. als kaputter Nicht-Package-Stub einer anderen
    Datei), wird __path__ nachgerüstet statt das Fehlen stillschweigend zu
    ignorieren.

    __path__ zeigt auf das ECHTE Verzeichnis (nicht []): ein leeres __path__
    macht `name` zwar zum Package, aber mit leerem Suchpfad — Python findet
    dann KEIN Submodul mehr (z.B. `models.user`), sobald diese Datei vor einer
    Datei läuft, die ein solches Submodul real importiert (Reihenfolge-
    abhängig, derselbe Mechanismus wie beim Befund
    zubu-sys-modules-stubs-ohne-path-brechen-submodul-importe).
    """
    mod = _ensure_stub(name)
    if not hasattr(mod, "__path__"):
        # Lokal berechnet statt der weiter unten definierten globalen
        # _BACKEND_DIR: diese Funktion wird bereits VOR jener Definition
        # aufgerufen (Zeile ~157 ff., _BACKEND_DIR erst ~Zeile 202).
        import os as _os_local

        _backend_dir = _os_local.path.normpath(
            _os_local.path.join(_os_local.path.dirname(__file__), "..")
        )
        mod.__path__ = [_os_local.path.join(_backend_dir, *name.split("."))]
    return mod


def _ensure_attr(module: types.ModuleType, attr: str, factory) -> None:
    """Setzt `attr` auf `module` nur, wenn es dort noch fehlt.

    Additiv statt destruktiv: ein bereits real geladenes Modul (mit echten
    SQLAlchemy-Factories) wird NICHT überschrieben — es fehlt dort ohnehin
    nichts. Ein (teilweise) kaputter Stub aus einer anderen Datei bekommt das
    fehlende Attribut deterministisch nachgerüstet.
    """
    if not hasattr(module, attr):
        setattr(module, attr, factory())


_models_pkg = _ensure_package("models")
_mb = _ensure_package("models.base")
_ensure_attr(_mb, "sync_session_factory", MagicMock)
# dependencies.py: `from models.base import async_session_factory`
_ensure_attr(_mb, "async_session_factory", MagicMock)

_mt = _ensure_package("models.tenant")
# dependencies.py: `from models.tenant import Tenant`
_ensure_attr(_mt, "Tenant", lambda: MagicMock)

# services.provider_resolver imports models.llm_provider — stub it to prevent ImportError
_mlp = _ensure_package("models.llm_provider")
_ensure_attr(_mlp, "LLMProvider", lambda: MagicMock)

# dependencies-Stub — DETERMINISTISCH, nicht vom evtl. gepollten Real-Modul
# abhängig. api/telegram.py importiert `from dependencies import get_db,
# get_tenant` nur als Depends()-Defaults für FastAPI-Routen; diese Tests rufen
# _send_telegram_message / _send_admin_telegram_message direkt auf, die echten
# Callables werden nie ausgeführt — simple Platzhalter genügen.
_deps_mod = _ensure_stub("dependencies")
if not hasattr(_deps_mod, "get_db"):

    async def _stub_get_db():
        yield MagicMock()

    _deps_mod.get_db = _stub_get_db
if not hasattr(_deps_mod, "get_tenant"):
    _deps_mod.get_tenant = MagicMock()

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
# Als Paket-Attribut registrieren: spec_from_file_location + exec_module setzt
# NUR sys.modules, nicht (wie ein regulärer `import services.telegram_token_resolver`)
# automatisch services.telegram_token_resolver = <mod>. Ohne dieses Attribut
# löst `patch("services.telegram_token_resolver.get_tenant_bot_token", …)` in
# einer NACHFOLGEND gesammelten Datei über pkgutil.resolve_name per
# `getattr(services, "telegram_token_resolver")` auf und wirft AttributeError —
# unabhängig vom sys.modules-Eintrag, der für den String-Pfad nicht befragt wird.
if "services" in sys.modules:
    sys.modules["services"].telegram_token_resolver = _ttr_mod

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
# Selbstgenügsamkeit gegen tests/conftest.py::pytest_collectstart (2026-09-17)
# ---------------------------------------------------------------------------
#
# conftest.py setzt "services.telegram_token_resolver" vor JEDER weiteren
# Collection (auch pro Klasse INNERHALB dieser Datei — collectstart feuert
# modul-intern) auf die beim allerersten collectstart eingefrorene Baseline
# zurück (_POLLUTION_PRONE_MODULES, conftest.py). Läuft diese Datei isoliert,
# ist diese Baseline "kein Eintrag" — der oben (Modul-Ebene, einmalig beim
# Import) gesetzte Stub verschwindet dann vor der zweiten Testklasse wieder
# und sys.modules["services.telegram_token_resolver"] wirft KeyError.
# Im Suiten-Kontext bleibt es unsichtbar, weil eine alphabetisch früher
# gesammelte Datei (z.B. test_telegram_poller.py) den Stub schon VOR dem
# allerersten collectstart gesetzt hat — dann ist er Teil der Baseline.
#
# Fix nach demselben Muster wie test_telegram_poller.py::_pin_api_telegram_stub:
# vor jedem Test in dieser Datei den eigenen Stand neu verankern, danach den
# zuvor vorgefundenen Zustand restaurieren (kein globaler Eingriff in conftest.py).
@pytest.fixture(autouse=True)
def _pin_telegram_token_resolver_stub():
    _prev = sys.modules.get("services.telegram_token_resolver")
    _prev_attr = getattr(sys.modules.get("services"), "telegram_token_resolver", None)
    sys.modules["services.telegram_token_resolver"] = _ttr_mod
    if "services" in sys.modules:
        sys.modules["services"].telegram_token_resolver = _ttr_mod
    try:
        yield
    finally:
        if _prev is not None:
            sys.modules["services.telegram_token_resolver"] = _prev
        else:
            sys.modules.pop("services.telegram_token_resolver", None)
        if "services" in sys.modules:
            if _prev_attr is not None:
                sys.modules["services"].telegram_token_resolver = _prev_attr
            else:
                sys.modules["services"].__dict__.pop("telegram_token_resolver", None)


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
        # Mock-Artefakt-Fix (2026-07-21): ein unkonfigurierter `patch("httpx.post")`
        # liefert eine bloße MagicMock als Response zurück. api/telegram.py prüft
        # `resp.status_code == 200 and tg_body.get("ok")` — eine MagicMock ist
        # NIE `== 200`, also wertet der Code jeden unkonfigurierten Mock als
        # fehlgeschlagenen Send (→ update_last_active wird korrekterweise NICHT
        # aufgerufen). Das ist kein Produktcode-Bug, sondern eine fehlende
        # Mock-Konfiguration — response muss wie in test_sends_when_bot_active
        # einen echten Erfolg (status_code=200, json().get("ok")=True) simulieren.
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

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
            patch("httpx.post", return_value=mock_response),
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

    def test_logs_outbound_row_on_telegram_rejection(self):
        """Telegram lehnt ab (z.B. 400 'chat not found') → telegram_message_log
        bekommt trotzdem eine 'out'/send_status='failed'-Zeile.

        Regression (21.08., real reproduziert gegen den Testserver): der
        INSERT dieses Zweigs nutzte ':payload::jsonb' — SQLAlchemys text()
        schneidet den Bind-Parameter-Namen am zweiten ':' ab ("payloa" statt
        "payload"), der INSERT scheiterte IMMER mit einem SyntaxError. Bei
        DEBUG-Logging war das unsichtbar (best-effort except-Block) — exakt
        Louis' Symptom: 90 in / 0 out, weil auch der Fehlerzweig nie schrieb.
        """
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "ok": False,
            "description": "Bad Request: chat not found",
        }

        db_mock = _make_db_mock()

        with (
            patch.object(
                sys.modules["services.telegram_token_resolver"],
                "get_tenant_bot_token",
                return_value="987654:TENANT_TOKEN",
            ),
            patch.object(tg, "sync_session_factory", return_value=db_mock),
            patch("httpx.post", return_value=mock_response),
        ):
            result = tg._send_telegram_message(999000001, "Test msg", tenant_id="tenant-abc")

        assert result is False
        insert_calls = [
            c
            for c in db_mock.execute.call_args_list
            if "INSERT INTO telegram_message_log" in str(c.args[0])
        ]
        assert len(insert_calls) == 1, "erwartet: genau ein Outbound-Log-INSERT beim Ablehnen"
        sql = str(insert_calls[0].args[0])
        assert "'out'" in sql
        payload = insert_calls[0].args[1]["payload"]
        assert '"send_status": "failed"' in payload

        bindparams = set(insert_calls[0].args[0]._bindparams.keys())
        assert "payload" in bindparams, (
            f"Bind-Parameter 'payload' fehlt (gefunden: {bindparams}) — "
            "vermutlich ':payload::jsonb' statt 'CAST(:payload AS jsonb)'"
        )

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

        # Regression (21.08.): `:payload::jsonb` (Postgres-Cast direkt hinterm
        # Bind-Parameter) wird von SQLAlchemys text()-Parser als zwei
        # getrennte Doppelpunkte gelesen — der Bind-Parameter-Name wird am
        # zweiten ':' abgeschnitten ("payloa" statt "payload"), der echte
        # INSERT scheitert IMMER mit einem SyntaxError, egal wie der Mock
        # aussieht. Ein reiner String-Check auf "'out'" haette das NIE
        # gefunden — nur die echten SQLAlchemy-Bindparameter zeigen es.
        bindparams = set(insert_calls[0].args[0]._bindparams.keys())
        assert "payload" in bindparams, (
            f"Bind-Parameter 'payload' fehlt (gefunden: {bindparams}) — "
            "vermutlich ':payload::jsonb' statt 'CAST(:payload AS jsonb)'"
        )

    def test_scheiterndes_outbound_log_insert_wird_nicht_stumm_verschluckt(self, caplog):
        """SSOT AP1.3 (21.08.): scheitert der Erfolgs-INSERT selbst (z.B. RLS-
        Policy-Verletzung), muss das auf WARNING erscheinen — nicht auf DEBUG.
        War es DEBUG, blieb ein erfolgreicher Send in telegram_message_log
        UNSICHTBAR, ohne dass irgendwo ein Log-Level das anzeigt (Louis' Fall:
        90 in / 0 out, obwohl Antworten laut seinen Screenshots ankamen)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        db_mock = _make_db_mock()
        db_mock.execute.side_effect = Exception("insert boom")

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
            caplog.at_level(logging.DEBUG),
        ):
            result = tg._send_telegram_message(12345, "Test msg", tenant_id="tenant-abc")

        # Der Send selbst bleibt erfolgreich (best-effort-Logging darf ihn nicht blockieren).
        assert result is True
        warnungen = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any(
            "telegram_message_log INSERT (sent) failed" in r.getMessage() for r in warnungen
        ), f"scheiternder Erfolgs-INSERT wurde nicht auf WARNING geloggt: {caplog.records}"


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


# ===========================================================================
# Tests: _draft_action_keyboard (Stufe 1: Approve/Regenerate/Reject-Buttons)
# ===========================================================================


class TestDraftActionKeyboard:
    def test_keyboard_has_three_actions_scoped_to_content_id(self):
        kb = tg._draft_action_keyboard("abc-123")
        rows = kb["inline_keyboard"]
        callbacks = [btn["callback_data"] for row in rows for btn in row]
        assert "cmd:approve:abc-123" in callbacks
        assert "cmd:regenerate:abc-123" in callbacks
        assert "cmd:reject:abc-123" in callbacks
        # Jeder Button trägt exakt die content_id → keine Verwechslung zwischen Drafts
        assert all(cb.endswith(":abc-123") for cb in callbacks)


# ===========================================================================
# Tests: _approve_content_sync (Stufe 1: tenant-scoped + idempotent)
# ===========================================================================


class TestApproveContentSync:
    def test_approves_draft_scoped_to_tenant(self):
        db = _make_db_mock(row=("draft",))  # SELECT status → 'draft'
        with patch.object(tg, "sync_session_factory", return_value=db):
            result = tg._approve_content_sync("cid-1", "tenant-a")
        assert result == "approved"
        # Genau ein UPDATE mit tenant-scope + telegram_button
        upd = [c for c in db.execute.call_args_list if "UPDATE content_pieces" in str(c.args[0])]
        assert len(upd) == 1
        assert "tenant_id = :tid" in str(upd[0].args[0])
        assert upd[0].args[1]["tid"] == "tenant-a"
        assert upd[0].args[1]["cid"] == "cid-1"
        # Exakte mandatierte Feldwerte — Regression auf einen davon muss rot schlagen
        assert "status = 'approved'" in str(upd[0].args[0])
        assert "approval_method = 'telegram_button'" in str(upd[0].args[0])
        assert "approved_by = 'telegram'" in str(upd[0].args[0])
        assert "approved_at = now()" in str(upd[0].args[0])

    def test_idempotent_when_already_approved(self):
        db = _make_db_mock(row=("approved",))
        with patch.object(tg, "sync_session_factory", return_value=db):
            result = tg._approve_content_sync("cid-1", "tenant-a")
        assert result == "already"
        assert not [
            c for c in db.execute.call_args_list if "UPDATE content_pieces" in str(c.args[0])
        ]

    def test_not_found_or_cross_tenant(self):
        db = _make_db_mock(row=None)  # kein Row für (cid, tenant)
        with patch.object(tg, "sync_session_factory", return_value=db):
            result = tg._approve_content_sync("cid-x", "tenant-b")
        assert result == "not_found"
        # Kein UPDATE — weder für ein nicht-existentes noch für ein fremdes Piece
        assert not [
            c for c in db.execute.call_args_list if "UPDATE content_pieces" in str(c.args[0])
        ]
        # SELECT war tenant-scoped auf genau den übergebenen Tenant
        sel = [c for c in db.execute.call_args_list if "SELECT status" in str(c.args[0])]
        assert sel[0].args[1]["tid"] == "tenant-b"

    def test_fail_open_on_db_error(self, caplog):
        db = _make_db_mock(row=("draft",))
        db.execute.side_effect = Exception("boom")
        with (
            patch.object(tg, "sync_session_factory", return_value=db),
            caplog.at_level(logging.WARNING),
        ):
            result = tg._approve_content_sync("cid-1", "tenant-a")
        assert result == "not_found"
        assert not [
            c for c in db.execute.call_args_list if "UPDATE content_pieces" in str(c.args[0])
        ]
        log_text = "\n".join(r.getMessage() for r in caplog.records)
        assert "boom" not in log_text, f"Exception-Message im Log gefunden: {log_text}"
        assert "Exception" in log_text, f"Exception-Klassenname fehlt im Log: {log_text}"


# ===========================================================================
# Tests: _reject_content_sync (Stufe 1: tenant-scoped + idempotent)
# ===========================================================================


class TestRejectContentSync:
    def test_rejects_draft_scoped_to_tenant(self):
        db = _make_db_mock(row=("draft",))
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._reject_content_sync("cid-1", "tenant-a") == "rejected"
        upd = [c for c in db.execute.call_args_list if "UPDATE content_pieces" in str(c.args[0])]
        assert len(upd) == 1 and "status = 'rejected'" in str(upd[0].args[0])
        assert "tenant_id = :tid" in str(upd[0].args[0])
        assert upd[0].args[1]["tid"] == "tenant-a"
        assert upd[0].args[1]["cid"] == "cid-1"

    def test_idempotent_when_already_rejected(self):
        db = _make_db_mock(row=("rejected",))
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._reject_content_sync("cid-1", "tenant-a") == "already"
        assert not [
            c for c in db.execute.call_args_list if "UPDATE content_pieces" in str(c.args[0])
        ]

    def test_not_found(self):
        db = _make_db_mock(row=None)
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._reject_content_sync("cid-x", "tenant-a") == "not_found"
        assert not [
            c for c in db.execute.call_args_list if "UPDATE content_pieces" in str(c.args[0])
        ]
        sel = [c for c in db.execute.call_args_list if "SELECT status" in str(c.args[0])]
        assert sel[0].args[1]["tid"] == "tenant-a"

    def test_fail_open_on_db_error(self, caplog):
        db = _make_db_mock(row=("draft",))
        db.execute.side_effect = Exception("boom")
        with (
            patch.object(tg, "sync_session_factory", return_value=db),
            caplog.at_level(logging.WARNING),
        ):
            result = tg._reject_content_sync("cid-1", "tenant-a")
        assert result == "not_found"
        assert not [
            c for c in db.execute.call_args_list if "UPDATE content_pieces" in str(c.args[0])
        ]
        log_text = "\n".join(r.getMessage() for r in caplog.records)
        assert "boom" not in log_text, f"Exception-Message im Log gefunden: {log_text}"
        assert "Exception" in log_text, f"Exception-Klassenname fehlt im Log: {log_text}"


# ===========================================================================
# Tests: _handle_callback_query — approve/reject/regenerate Dispatch (Stufe 1)
# ===========================================================================


class TestApproveRejectRegenerateCallbacks:
    def _cq(self, data):
        return {"id": "cq1", "data": data, "from": {"id": 5}, "message": {"chat": {"id": 99}}}

    def test_approve_callback_calls_sync_and_confirms(self):
        with (
            patch.object(tg, "_approve_content_sync", return_value="approved") as appr,
            patch.object(tg, "_send_telegram_message") as send,
            patch("httpx.post"),
        ):
            tg._handle_callback_query(self._cq("cmd:approve:cid-1"), known_tenant_id="tenant-a")
        appr.assert_called_once_with("cid-1", "tenant-a")  # tenant-scoped
        assert send.called and "✅" in send.call_args.args[1]

    def test_reject_callback_calls_sync(self):
        with (
            patch.object(tg, "_reject_content_sync", return_value="rejected") as rej,
            patch.object(tg, "_send_telegram_message"),
            patch("httpx.post"),
        ):
            tg._handle_callback_query(self._cq("cmd:reject:cid-1"), known_tenant_id="tenant-a")
        rej.assert_called_once_with("cid-1", "tenant-a")

    def test_regenerate_callback_enqueues_feedback_task(self):
        fake_task = MagicMock()
        with (
            patch.dict(
                sys.modules,
                {"tasks.post_feedback_task": MagicMock(regenerate_post_from_feedback=fake_task)},
            ),
            patch.object(tg, "_send_telegram_message"),
            patch("httpx.post"),
        ):
            tg._handle_callback_query(self._cq("cmd:regenerate:cid-1"), known_tenant_id="tenant-a")
        assert fake_task.apply_async.called
        args = (
            fake_task.apply_async.call_args.kwargs.get("args")
            or fake_task.apply_async.call_args.args[0]
        )
        assert (
            args[0] == "cid-1" and args[1] == "tenant-a"
        )  # (post_id, tenant_id, feedback, log_id)
