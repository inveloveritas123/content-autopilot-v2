"""Tests für die Inbound-Intent-Routing-Verdrahtung in tasks/telegram_task.py (Issue #16).

Wirft den Intent-Routing-Flow (extract_intent_features → route_telegram_intent →
p08_response) an, nachdem ein eingehender Telegram-/WhatsApp-Text bzw. eine
Voice-Antwort als memory_chunk gespeichert wurde.

Stub-Schicht (analog zu test_p08_service.py):
  Die lokale Test-venv hat KEIN sqlalchemy/celery/google/anthropic. Daher werden
  alle schweren Module VOR dem ersten Import von tasks.telegram_task gestubbt und
  das Modul danach direkt via importlib geladen. Alle DB-/Celery-/Service-Seams
  werden in den Tests gepatcht — kein realer DB-/Netzwerk-Zugriff.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stubs — MÜSSEN vor dem ersten Import von tasks.telegram_task gesetzt sein.
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_STUBBED_HERE = []


def _stub_mod(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    _STUBBED_HERE.append(name)
    return mod


# httpx — von telegram_task auf Modulebene importiert
if "httpx" not in sys.modules:
    _hx = _stub_mod("httpx")
    _hx.Client = MagicMock
    _hx.TimeoutException = type("TimeoutException", (Exception,), {})
    _hx.RequestError = type("RequestError", (Exception,), {})

# sqlalchemy + Untermodule
if "sqlalchemy" not in sys.modules:
    _sq = _stub_mod("sqlalchemy")
    _sq.text = lambda q: q
for _name in ["sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"]:
    if _name not in sys.modules:
        _m = _stub_mod(_name)
        if _name == "sqlalchemy.ext.asyncio":
            _m.AsyncSession = MagicMock
            _m.create_async_engine = MagicMock()
        if _name == "sqlalchemy.orm":
            _m.sessionmaker = MagicMock()

# config.settings
if "config" not in sys.modules:
    _cfg = _stub_mod("config")
    _cfg.settings = types.SimpleNamespace(
        telegram_bot_token="test-token",
        database_url="postgresql+asyncpg://t:t@localhost/t",
    )

# models.base — sync_session_factory wird in Tests gepatcht
if "models" not in sys.modules:
    _stub_mod("models")
if "models.base" not in sys.modules:
    _mb = _stub_mod("models.base")
    _mb.sync_session_factory = MagicMock()

# services + Voice-Transcription (von telegram_task auf Modulebene importiert)
if "services" not in sys.modules:
    _stub_mod("services")
if "services.voice_transcription" not in sys.modules:
    _vt = _stub_mod("services.voice_transcription")

    class _TranscriptionError(Exception):
        pass

    class _TranscriptionResult:
        def __init__(self, text="", model_name="whisper", confidence=0.9):
            self.text = text
            self.model_name = model_name
            self.confidence = confidence

    _vt.TranscriptionError = _TranscriptionError
    _vt.TranscriptionResult = _TranscriptionResult
    _vt.transcribe_voice = MagicMock()

# Routing-/p08-Service-Stubs — lazy importiert in _route_inbound_message.
# Attribute werden je Test via @patch ersetzt. Die Submodule MÜSSEN als Attribut
# des services-Pakets registriert sein, damit @patch("services.<mod>.<fn>") den
# Target über getattr(services_pkg, "<mod>") auflösen kann.
_svc_pkg = sys.modules["services"]
if "services.layer1_extraction" not in sys.modules:
    _l1 = _stub_mod("services.layer1_extraction")
    _l1.extract_intent_features = MagicMock()
    _svc_pkg.layer1_extraction = _l1
if "services.layer2_routing" not in sys.modules:
    _l2 = _stub_mod("services.layer2_routing")
    _l2.route_telegram_intent = MagicMock()
    _svc_pkg.layer2_routing = _l2
if "services.p08_service" not in sys.modules:
    _p08 = _stub_mod("services.p08_service")
    _p08.p08_response = MagicMock()
    _svc_pkg.p08_service = _p08
# voice_transcription ebenfalls als Attribut registrieren (Konsistenz)
_svc_pkg.voice_transcription = sys.modules["services.voice_transcription"]

# celery — telegram_task importiert tasks.celery_app.celery_app und nutzt @celery_app.task
if "celery" not in sys.modules:
    _cel = _stub_mod("celery")


class _FakeCeleryApp:
    def task(self, *a, **kw):
        def deco(fn):
            return fn

        return deco


if "tasks" not in sys.modules:
    _stub_mod("tasks")
if "tasks.celery_app" not in sys.modules:
    _ca = _stub_mod("tasks.celery_app")
    _ca.celery_app = _FakeCeleryApp()

# ---------------------------------------------------------------------------
# tasks.telegram_task direkt laden (bypass tasks/__init__.py-Seiteneffekte)
# ---------------------------------------------------------------------------
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "tasks.telegram_task",
    os.path.join(_BACKEND_DIR, "tasks", "telegram_task.py"),
)
_tt = _ilu.module_from_spec(_spec)
sys.modules["tasks.telegram_task"] = _tt
_spec.loader.exec_module(_tt)

# Als Attribut des tasks-Pakets registrieren, damit @patch("tasks.telegram_task.*")
# über getattr(tasks_pkg, "telegram_task") aufgelöst werden kann.
sys.modules["tasks"].telegram_task = _tt


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------


def _make_extraction(intent="answer_to_question"):
    return types.SimpleNamespace(
        intent=intent,
        session_context="active_response",
        extracted_features={"key_insight": "wir wachsen"},
        flagged_for_review=False,
        flag_reasons=[],
        routed_to="ok",
    )


def _make_decision(target, payload=None):
    return types.SimpleNamespace(target=target, payload=payload or {})


def _make_p08_result(next_action="vertiefen"):
    return types.SimpleNamespace(
        next_action=next_action,
        message="Erzähl mir mehr.",
        quality="gold",
        session_id="sess-1",
        is_closed=False,
    )


def _active_session():
    return types.SimpleNamespace(id="sess-1", status="active")


# ---------------------------------------------------------------------------
# _process_text — Routing-Tests
# ---------------------------------------------------------------------------


class TestProcessTextRouting:
    @patch("services.p08_service.p08_response")
    @patch("services.layer2_routing.route_telegram_intent")
    @patch("services.layer1_extraction.extract_intent_features")
    @patch("tasks.telegram_task._load_active_session")
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_active_session_answer_routes_to_p08(
        self,
        mock_run,
        mock_store,
        mock_load_session,
        mock_extract,
        mock_route,
        mock_p08,
    ):
        mock_run.return_value = "chunk-123"
        mock_load_session.return_value = _active_session()
        mock_extract.return_value = _make_extraction("answer_to_question")
        mock_route.return_value = _make_decision(
            "p08_response", {"session_id": "sess-1", "features": {"k": "v"}}
        )
        mock_p08.return_value = _make_p08_result(next_action="vertiefen")

        payload = {"text": "Das ist eine ausführliche Antwort auf deine Frage."}
        result = _tt._process_text("log-1", "tenant-1", payload)

        assert result["status"] == "ok"
        assert result["memory_chunk_id"] == "chunk-123"
        assert result["routed_to"] == "p08_response"
        assert result["p08_next_action"] == "vertiefen"
        assert result["bot_session_id"] == "sess-1"
        # p08_response genau einmal mit (session_id, features)
        mock_p08.assert_called_once_with("sess-1", {"k": "v"})

    @patch("services.p08_service.p08_response")
    @patch("services.layer1_extraction.extract_intent_features")
    @patch("tasks.telegram_task._load_active_session")
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_no_active_session_does_not_route(
        self, mock_run, mock_store, mock_load_session, mock_extract, mock_p08
    ):
        mock_run.return_value = "chunk-xyz"
        mock_load_session.return_value = None

        payload = {"text": "Irgendeine Notiz die lang genug ist."}
        result = _tt._process_text("log-2", "tenant-1", payload)

        assert result["status"] == "ok"
        assert result["memory_chunk_id"] == "chunk-xyz"
        assert "routed_to" not in result
        mock_extract.assert_not_called()
        mock_p08.assert_not_called()

    @patch("services.p08_service.p08_response")
    @patch("services.layer2_routing.route_telegram_intent")
    @patch("services.layer1_extraction.extract_intent_features")
    @patch("tasks.telegram_task._load_active_session")
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_non_p08_target_sets_routed_to_but_no_p08(
        self, mock_run, mock_store, mock_load_session, mock_extract, mock_route, mock_p08
    ):
        mock_run.return_value = "chunk-r"
        mock_load_session.return_value = _active_session()
        mock_extract.return_value = _make_extraction("spontaneous_idea")
        mock_route.return_value = _make_decision("reviewer_queue", {})

        payload = {"text": "Eine spontane Idee die lang genug ist."}
        result = _tt._process_text("log-3", "tenant-1", payload)

        assert result["status"] == "ok"
        assert result["routed_to"] == "reviewer_queue"
        assert "p08_next_action" not in result
        mock_p08.assert_not_called()

    @patch("services.p08_service.p08_response")
    @patch("services.layer1_extraction.extract_intent_features")
    @patch("tasks.telegram_task._load_active_session")
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_fail_open_on_extract_exception(
        self, mock_run, mock_store, mock_load_session, mock_extract, mock_p08
    ):
        mock_run.return_value = "chunk-fail"
        mock_load_session.return_value = _active_session()
        mock_extract.side_effect = RuntimeError("layer1 boom")

        payload = {"text": "Antwort die einen Routing-Fehler auslöst."}
        result = _tt._process_text("log-4", "tenant-1", payload)

        # Chunk-Ergebnis bleibt intakt, kein Crash, kein routed_to
        assert result["status"] == "ok"
        assert result["memory_chunk_id"] == "chunk-fail"
        assert "routed_to" not in result
        mock_p08.assert_not_called()

    @patch("services.p08_service.p08_response")
    @patch("services.layer2_routing.route_telegram_intent")
    @patch("services.layer1_extraction.extract_intent_features")
    @patch("tasks.telegram_task._load_active_session")
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_fail_open_on_p08_exception(
        self, mock_run, mock_store, mock_load_session, mock_extract, mock_route, mock_p08
    ):
        # Kern des Fail-open-Versprechens: wirft p08_response, darf das Routing-Dict
        # NICHT halb appliziert werden — Chunk-Return bleibt komplett intakt.
        mock_run.return_value = "chunk-p08fail"
        mock_load_session.return_value = _active_session()
        mock_extract.return_value = _make_extraction("answer_to_question")
        mock_route.return_value = _make_decision(
            "p08_response", {"session_id": "sess-1", "features": {"k": "v"}}
        )
        mock_p08.side_effect = RuntimeError("p08 boom")

        payload = {"text": "Antwort, deren p08-Verarbeitung crasht."}
        result = _tt._process_text("log-5", "tenant-1", payload)

        assert result["status"] == "ok"
        assert result["memory_chunk_id"] == "chunk-p08fail"
        assert "routed_to" not in result
        assert "p08_next_action" not in result


# ---------------------------------------------------------------------------
# _process_voice — Routing-Tests
# ---------------------------------------------------------------------------


class TestProcessVoiceRouting:
    @patch("services.p08_service.p08_response")
    @patch("services.layer2_routing.route_telegram_intent")
    @patch("services.layer1_extraction.extract_intent_features")
    @patch("tasks.telegram_task._load_active_session")
    @patch("tasks.telegram_task._update_log_transcript")
    @patch("tasks.telegram_task.transcribe_voice")
    @patch("tasks.telegram_task._telegram_get_file")
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_voice_active_session_routes_transcript_to_p08(
        self,
        mock_run,
        mock_store,
        mock_get_file,
        mock_transcribe,
        mock_update_log,
        mock_load_session,
        mock_extract,
        mock_route,
        mock_p08,
    ):
        TRANSCRIPT = "Das ist die gesprochene Antwort auf die Bot-Frage."
        mock_get_file.return_value = b"audio-bytes"
        mock_transcribe.return_value = types.SimpleNamespace(
            text=TRANSCRIPT, model_name="whisper", confidence=0.95
        )
        mock_run.return_value = "voice-chunk-1"
        mock_load_session.return_value = _active_session()
        mock_extract.return_value = _make_extraction("answer_to_question")
        mock_route.return_value = _make_decision(
            "p08_response", {"session_id": "sess-1", "features": {"k": "v"}}
        )
        mock_p08.return_value = _make_p08_result(next_action="vertiefen")

        payload = {"voice": {"file_id": "f1", "duration": 12, "mime_type": "audio/ogg"}}
        result = _tt._process_voice("log-v", "tenant-1", payload)

        assert result["status"] == "ok"
        assert result["memory_chunk_id"] == "voice-chunk-1"
        assert result["routed_to"] == "p08_response"
        assert result["p08_next_action"] == "vertiefen"
        # Transkript wurde an extract_intent_features übergeben
        kw = mock_extract.call_args.kwargs
        assert kw["transcript"] == TRANSCRIPT
        assert kw["session_state"] == "active"
        mock_p08.assert_called_once()
