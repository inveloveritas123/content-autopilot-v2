"""Tests für die Inbound-Intent-Routing-Verdrahtung in tasks/telegram_task.py (Issue #16).

Wirft den Intent-Routing-Flow (extract_intent_features → route_telegram_intent →
p08_response) an, nachdem ein eingehender Telegram-/WhatsApp-Text bzw. eine
Voice-Antwort als memory_chunk gespeichert wurde.

Stub-Schicht wird vollständig von tests._telegram_task_env bereitgestellt —
keine eigene spec_from_file_location/Stub-Logik mehr. Beide Test-Dateien
(test_telegram_inbound_routing + test_idempotency_routing) teilen so eine
einzige Modulinstanz von tasks.telegram_task und können in beliebiger
Reihenfolge kombiniert laufen (Issue #16, #18, #56, #57).
"""

import sys
import types
from unittest.mock import MagicMock, patch

# Gemeinsame Stub-Umgebung + Modul-Instanz
from tests._telegram_task_env import (  # noqa: E402
    active_session,
    make_decision,
    make_extraction,
    make_guard_db_mock,
    make_p08_result,
    tt,
)


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
        mock_load_session.return_value = active_session()
        mock_extract.return_value = make_extraction("answer_to_question")
        mock_route.return_value = make_decision(
            "p08_response", {"session_id": "sess-1", "features": {"k": "v"}}
        )
        mock_p08.return_value = make_p08_result(next_action="vertiefen")

        payload = {"text": "Das ist eine ausführliche Antwort auf deine Frage."}
        # #56: sync_session_factory wird für Guard-SELECT gebraucht → (None,) = noch nicht geroutet
        with patch("tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)):
            result = tt._process_text("log-1", "tenant-1", payload)

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
        with patch("tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)):
            result = tt._process_text("log-2", "tenant-1", payload)

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
        mock_load_session.return_value = active_session()
        mock_extract.return_value = make_extraction("spontaneous_idea")
        mock_route.return_value = make_decision("reviewer_queue", {})

        payload = {"text": "Eine spontane Idee die lang genug ist."}
        with patch("tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)):
            result = tt._process_text("log-3", "tenant-1", payload)

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
        mock_load_session.return_value = active_session()
        mock_extract.side_effect = RuntimeError("layer1 boom")

        payload = {"text": "Antwort die einen Routing-Fehler auslöst."}
        with patch("tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)):
            result = tt._process_text("log-4", "tenant-1", payload)

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
        mock_load_session.return_value = active_session()
        mock_extract.return_value = make_extraction("answer_to_question")
        mock_route.return_value = make_decision(
            "p08_response", {"session_id": "sess-1", "features": {"k": "v"}}
        )
        mock_p08.side_effect = RuntimeError("p08 boom")

        payload = {"text": "Antwort, deren p08-Verarbeitung crasht."}
        with patch("tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)):
            result = tt._process_text("log-5", "tenant-1", payload)

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
        mock_load_session.return_value = active_session()
        mock_extract.return_value = make_extraction("answer_to_question")
        mock_route.return_value = make_decision(
            "p08_response", {"session_id": "sess-1", "features": {"k": "v"}}
        )
        mock_p08.return_value = make_p08_result(next_action="vertiefen")

        payload = {"voice": {"file_id": "f1", "duration": 12, "mime_type": "audio/ogg"}}
        # #56: Guard-SELECT für log_id="log-v" → (None,) = noch nicht geroutet
        with patch("tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)):
            result = tt._process_voice("log-v", "tenant-1", payload)

        assert result["status"] == "ok"
        assert result["memory_chunk_id"] == "voice-chunk-1"
        assert result["routed_to"] == "p08_response"
        assert result["p08_next_action"] == "vertiefen"
        # Transkript wurde an extract_intent_features übergeben
        kw = mock_extract.call_args.kwargs
        assert kw["transcript"] == TRANSCRIPT
        assert kw["session_state"] == "active"
        mock_p08.assert_called_once()
