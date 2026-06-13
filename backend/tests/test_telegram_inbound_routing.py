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
from tests._telegram_task_env import (
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


# ---------------------------------------------------------------------------
# #17 — Folgefrage / Abschluss per Telegram zurücksenden
# ---------------------------------------------------------------------------


class TestFollowupMessageSend:
    """#17: _route_inbound_message sendet result.message via _send_telegram_message zurück.

    Patch-Strategie:
      - services.p08_service.p08_response  — Stub-Modul-Binding (lazy import)
      - tasks.telegram_task._resolve_chat_id — direkte Attribut-Ersetzung
      - api.telegram._send_telegram_message — Stub-Modul-Binding (lazy import)
      - tasks.telegram_task.sync_session_factory — Idempotenz-Guard-SELECT
    """

    def _run_route(
        self,
        p08_result,
        chat_id_return,
        send_mock,
        decision_target="p08_response",
    ):
        """Hilfsmethode: _route_inbound_message mit allen Stubs fahren."""

        with (
            patch.object(tt, "_load_active_session", return_value=active_session()),
            patch.object(
                sys.modules["services.layer1_extraction"],
                "extract_intent_features",
                return_value=make_extraction("answer_to_question"),
            ),
            patch.object(
                sys.modules["services.layer2_routing"],
                "route_telegram_intent",
                return_value=make_decision(
                    decision_target,
                    {"session_id": "sess-1", "features": {"k": "v"}},
                ),
            ),
            patch.object(
                sys.modules["services.p08_service"],
                "p08_response",
                return_value=p08_result,
            ),
            patch.object(tt, "_resolve_chat_id", return_value=chat_id_return),
            patch.object(sys.modules["api.telegram"], "_send_telegram_message", send_mock),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
        ):
            return tt._route_inbound_message("tenant-1", "Meine Antwort", log_id="log-17")

    def test_followup_question_sent(self):
        """Aktive Session + Antwort → Folgefrage wird via _send_telegram_message gesendet."""
        send_mock = MagicMock()
        p08_result = make_p08_result(
            next_action="vertiefen",
            message="Frage 2?",
            is_closed=False,
        )

        result = self._run_route(p08_result, chat_id_return=4711, send_mock=send_mock)

        assert result is not None
        assert result["p08_message_sent"] is True
        send_mock.assert_called_once_with(4711, "Frage 2?")

    def test_close_message_sent(self):
        """Session-Abschluss (is_closed=True) → Abschluss-Text wird gesendet."""
        send_mock = MagicMock()
        p08_result = make_p08_result(
            next_action="close",
            message="Danke! Ich habe genug Material gesammelt.",
            is_closed=True,
        )

        result = self._run_route(p08_result, chat_id_return=9999, send_mock=send_mock)

        assert result is not None
        assert result["p08_message_sent"] is True
        send_mock.assert_called_once_with(9999, "Danke! Ich habe genug Material gesammelt.")

    def test_no_chat_link_no_send(self):
        """Kein aktiver tenant_telegram_link → kein Send, p08_message_sent False, kein Raise."""
        send_mock = MagicMock()
        p08_result = make_p08_result(next_action="vertiefen", message="Frage?", is_closed=False)

        result = self._run_route(p08_result, chat_id_return=None, send_mock=send_mock)

        assert result is not None
        assert result["p08_message_sent"] is False
        send_mock.assert_not_called()

    def test_send_failure_fail_open(self):
        """_send_telegram_message wirft → routing_info bleibt intakt, kein Raise."""

        crashing_send = MagicMock(side_effect=RuntimeError("Telegram down"))
        p08_result = make_p08_result(next_action="vertiefen", message="Frage?", is_closed=False)

        result = self._run_route(p08_result, chat_id_return=1234, send_mock=crashing_send)

        # Chunk-Return bleibt intakt (kein raise, kein None)
        assert result is not None
        # routed_to muss gesetzt sein
        assert result.get("routed_to") == "p08_response"
        # p08_message_sent muss False sein (Send fehlgeschlagen)
        assert result["p08_message_sent"] is False

    def test_non_p08_target_no_send(self):
        """Routing-Target != p08_response → kein Send, kein p08_message_sent-Key."""
        send_mock = MagicMock()
        # p08_result wird bei reviewer_queue gar nicht ausgewertet
        p08_result = make_p08_result()

        result = self._run_route(
            p08_result,
            chat_id_return=4711,
            send_mock=send_mock,
            decision_target="reviewer_queue",
        )

        assert result is not None
        assert result["routed_to"] == "reviewer_queue"
        assert "p08_message_sent" not in result
        send_mock.assert_not_called()
