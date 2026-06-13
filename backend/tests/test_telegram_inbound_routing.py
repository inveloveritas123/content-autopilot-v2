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
        with patch(
            "tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)
        ):
            result = tt._process_text("log-1", "tenant-1", payload)

        assert result["status"] == "ok"
        assert result["memory_chunk_id"] == "chunk-123"
        assert result["routed_to"] == "p08_response"
        assert result["p08_next_action"] == "vertiefen"
        assert result["bot_session_id"] == "sess-1"
        # p08_response genau einmal mit (session_id, features, raw_transcript).
        # #19: text_content wird als raw_transcript durchgereicht (Schicht-3:
        # p08 persistiert es in der Session, nie in den Prompt).
        mock_p08.assert_called_once_with(
            "sess-1",
            {"k": "v"},
            raw_transcript="Das ist eine ausführliche Antwort auf deine Frage.",
        )

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
        with patch(
            "tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)
        ):
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
        with patch(
            "tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)
        ):
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
        with patch(
            "tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)
        ):
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
        with patch(
            "tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)
        ):
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
        with patch(
            "tasks.telegram_task.sync_session_factory", return_value=make_guard_db_mock(None)
        ):
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
        send_mock.assert_called_once_with(4711, "Frage 2?", tenant_id="tenant-1")

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
        send_mock.assert_called_once_with(
            9999, "Danke! Ich habe genug Material gesammelt.", tenant_id="tenant-1"
        )

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


class TestClosePostGenerationTrigger:
    """#19: Echter Session-Close → session_post_task wird enqueued.

    Nur ein active→closed-Übergang (is_closed=True, was_already_closed=False)
    triggert apply_async. Spät-/Doppel-Events auf eine bereits geschlossene
    Session (was_already_closed=True) triggern NICHT. Enqueue ist fail-open.
    """

    def _run_route(self, p08_result):
        """Fährt _route_inbound_message und gibt (result, gen_task_mock) zurück.

        generate_post_from_session wird komplett durch einen MagicMock ersetzt
        (dessen .apply_async automatisch existiert) — robust unabhängig davon,
        ob das echte Task-Modul oder der Env-Stub in sys.modules liegt.
        """
        import sys

        gen_task_mock = MagicMock()
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
                    "p08_response", {"session_id": "sess-1", "features": {"k": "v"}}
                ),
            ),
            patch.object(
                sys.modules["services.p08_service"],
                "p08_response",
                return_value=p08_result,
            ),
            # chat_id/Send sind für den Trigger irrelevant — neutralisieren.
            patch.object(tt, "_resolve_chat_id", return_value=4711),
            patch.object(sys.modules["api.telegram"], "_send_telegram_message", MagicMock()),
            patch.object(
                sys.modules["tasks.session_post_task"],
                "generate_post_from_session",
                gen_task_mock,
            ),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
        ):
            result = tt._route_inbound_message("tenant-1", "Meine Antwort", log_id="log-19")
        return result, gen_task_mock

    def test_close_triggers_post_task_once(self):
        """Echter Close (was_already_closed=False) → apply_async genau 1× mit (session_id, tenant_id)."""
        p08_result = make_p08_result(
            next_action="close",
            message="Danke!",
            is_closed=True,
            was_already_closed=False,
        )

        result, gen_task = self._run_route(p08_result)

        assert result is not None
        assert result.get("post_generation_enqueued") is True
        gen_task.apply_async.assert_called_once_with(args=["sess-1", "tenant-1"])

    def test_already_closed_does_not_trigger(self):
        """Spät-Event auf geschlossene Session (was_already_closed=True) → kein Enqueue."""
        p08_result = make_p08_result(
            next_action="close",
            message="Session beendet.",
            is_closed=True,
            was_already_closed=True,
        )

        result, gen_task = self._run_route(p08_result)

        assert result is not None
        gen_task.apply_async.assert_not_called()
        assert "post_generation_enqueued" not in result

    def test_followup_does_not_trigger(self):
        """Vertiefen (is_closed=False) → kein Post-Task enqueued."""
        p08_result = make_p08_result(
            next_action="vertiefen",
            message="Frage 2?",
            is_closed=False,
        )

        result, gen_task = self._run_route(p08_result)

        assert result is not None
        gen_task.apply_async.assert_not_called()

    def test_enqueue_failure_fail_open(self):
        """apply_async wirft → routing_info bleibt intakt, kein Raise."""
        p08_result = make_p08_result(
            next_action="close",
            message="Danke!",
            is_closed=True,
            was_already_closed=False,
        )

        result, gen_task = self._run_route_with_crash(p08_result)

        assert result is not None
        assert result.get("routed_to") == "p08_response"
        assert result.get("post_generation_enqueued") is False

    def _run_route_with_crash(self, p08_result):
        """Wie _run_route, aber apply_async wirft (fail-open-Test)."""
        import sys

        gen_task_mock = MagicMock()
        gen_task_mock.apply_async.side_effect = RuntimeError("broker down")
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
                    "p08_response", {"session_id": "sess-1", "features": {"k": "v"}}
                ),
            ),
            patch.object(
                sys.modules["services.p08_service"],
                "p08_response",
                return_value=p08_result,
            ),
            patch.object(tt, "_resolve_chat_id", return_value=4711),
            patch.object(sys.modules["api.telegram"], "_send_telegram_message", MagicMock()),
            patch.object(
                sys.modules["tasks.session_post_task"],
                "generate_post_from_session",
                gen_task_mock,
            ),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
        ):
            result = tt._route_inbound_message("tenant-1", "Meine Antwort", log_id="log-19")
        return result, gen_task_mock


# ---------------------------------------------------------------------------
# #37 — Feedback-Loop: kein aktive Session → letzter Post → regenerate_post_from_feedback
# ---------------------------------------------------------------------------


def _make_last_post(post_id="post-42", summary="Mein letzter Post.", bot_session_id="sess-1"):
    """Erzeugt ein SimpleNamespace das _resolve_last_post() zurückgeben würde."""
    return types.SimpleNamespace(id=post_id, summary=summary, bot_session_id=bot_session_id)


class TestFeedbackLoopRouting:
    """#37: Keine aktive Session + letzter Post + post_feedback-Intent
    → regenerate_post_from_feedback enqueued (fail-open).

    Alle Tests patchen _load_active_session=None, _resolve_last_post=<Wert>,
    extract_intent_features, route_telegram_intent und das Post-Feedback-Task.
    """

    def _run(
        self,
        last_post,
        extraction_intent="post_feedback",
        decision_target="voice_feedback_api",
        enqueue_side_effect=None,
    ):
        """Führt _route_inbound_message im Feedback-Pfad aus und gibt
        (result, regen_task_mock) zurück."""
        regen_mock = MagicMock()
        if enqueue_side_effect is not None:
            regen_mock.apply_async.side_effect = enqueue_side_effect

        with (
            patch.object(tt, "_load_active_session", return_value=None),
            patch.object(tt, "_resolve_last_post", return_value=last_post),
            patch.object(
                sys.modules["services.layer1_extraction"],
                "extract_intent_features",
                return_value=make_extraction(extraction_intent),
            ),
            patch.object(
                sys.modules["services.layer2_routing"],
                "route_telegram_intent",
                return_value=make_decision(decision_target, {}),
            ),
            patch.object(
                sys.modules["services.layer2_routing"],
                "persist_routing_decision",
                MagicMock(),
            ),
            patch.object(
                sys.modules["tasks.post_feedback_task"],
                "regenerate_post_from_feedback",
                regen_mock,
            ),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
        ):
            result = tt._route_inbound_message(
                "tenant-1", "Das war zu lang, mach kürzer!", log_id="log-37"
            )
        return result, regen_mock

    def test_no_session_no_last_post_returns_none(self):
        """Regression: keine Session + kein letzter Post → None wie heute."""
        with (
            patch.object(tt, "_load_active_session", return_value=None),
            patch.object(tt, "_resolve_last_post", return_value=None),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
        ):
            result = tt._route_inbound_message("tenant-1", "Irgendeine Notiz", log_id="log-37b")
        assert result is None

    def test_no_session_last_post_feedback_intent_enqueues(self):
        """Keine Session + letzter Post + post_feedback-Intent → Enqueue mit korrekten Args."""
        last_post = _make_last_post("post-42", "Mein Post.", "sess-1")
        result, regen_mock = self._run(last_post)

        assert result is not None
        assert result.get("routed_to") == "voice_feedback_api"
        assert result.get("regen_enqueued") is True
        regen_mock.apply_async.assert_called_once()
        call_args = regen_mock.apply_async.call_args
        # args: [last_post.id, tenant_id, feedback_text, log_id]
        positional_args = call_args[1].get("args") or call_args[0][0]
        assert positional_args[0] == "post-42"
        assert positional_args[1] == "tenant-1"
        assert "log-37" in str(positional_args)

    def test_no_session_last_post_smalltalk_no_enqueue(self):
        """Keine Session + letzter Post + smalltalk-Intent → kein Enqueue, kein Chat-Spam."""
        last_post = _make_last_post()
        result, regen_mock = self._run(
            last_post, extraction_intent="smalltalk", decision_target="close_friendly"
        )
        # Ergebnis darf nicht None sein (routing lief), aber kein Enqueue
        assert result is not None
        assert result.get("routed_to") == "close_friendly"
        regen_mock.apply_async.assert_not_called()

    def test_enqueue_failure_fail_open(self):
        """apply_async wirft → routing_info bleibt intakt, kein Raise, regen_enqueued=False."""
        last_post = _make_last_post()
        result, regen_mock = self._run(last_post, enqueue_side_effect=RuntimeError("broker down"))
        assert result is not None
        assert result.get("routed_to") == "voice_feedback_api"
        assert result.get("regen_enqueued") is False

    def test_active_session_path_unchanged(self):
        """Regression: aktive Session vorhanden → bestehender p08-Pfad läuft,
        _resolve_last_post wird NICHT aufgerufen."""
        resolve_mock = MagicMock()
        p08_mock = MagicMock(return_value=make_p08_result())
        with (
            patch.object(tt, "_load_active_session", return_value=active_session()),
            patch.object(tt, "_resolve_last_post", resolve_mock),
            patch.object(
                sys.modules["services.layer1_extraction"],
                "extract_intent_features",
                return_value=make_extraction("answer_to_question"),
            ),
            patch.object(
                sys.modules["services.layer2_routing"],
                "route_telegram_intent",
                return_value=make_decision(
                    "p08_response", {"session_id": "sess-1", "features": {}}
                ),
            ),
            patch.object(sys.modules["services.p08_service"], "p08_response", p08_mock),
            patch.object(tt, "_resolve_chat_id", return_value=None),
            patch.object(sys.modules["api.telegram"], "_send_telegram_message", MagicMock()),
            patch.object(
                sys.modules["tasks.session_post_task"],
                "generate_post_from_session",
                MagicMock(),
            ),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
        ):
            result = tt._route_inbound_message("tenant-1", "Antwort", log_id="log-active")
        assert result is not None
        assert result.get("routed_to") == "p08_response"
        resolve_mock.assert_not_called()


class TestPersistMappingFix:
    """#37/D5: persist_routing_decision mappt voice_feedback_api → voice_feedback
    (CHECK-Constraint in migration 019:66 kennt nur 'voice_feedback', nicht '_api').
    """

    def test_voice_feedback_api_mapped_to_voice_feedback(self):
        """voice_feedback_api → voice_feedback vor dem UPDATE.

        Testet die Mapping-Logik über _ROUTED_TO_MAP und einen direkten
        persist_routing_decision-Aufruf auf dem echten Modulcode.

        Strategie: persist_routing_decision über den bereits geladenen (echten oder
        gestubbt) layer2_routing-Eintrag aus sys.modules aufrufen — der Stub hat
        jedoch keine _ROUTED_TO_MAP. Daher direkt die Mapping-Konstante prüfen,
        die in der echten Datei definiert ist (über den Helfer sys.modules im
        echten Modul-Kontext, das per spec_from_file_location unter dem vollen
        Paketnamen registriert und in sys.modules eingetragen wird).
        """
        import importlib.util as _ilu
        import os as _os

        _BACKEND = _os.path.normpath(_os.path.join(_os.path.dirname(__file__), ".."))
        _MOD_NAME = "services.layer2_routing"

        # Echtes Modul laden — falls Stub drin ist (kein _ROUTED_TO_MAP), ersetzen.
        _existing = sys.modules.get(_MOD_NAME)
        need_load = _existing is None or not hasattr(_existing, "_ROUTED_TO_MAP")
        if need_load:
            _spec = _ilu.spec_from_file_location(
                _MOD_NAME,
                _os.path.join(_BACKEND, "services", "layer2_routing.py"),
            )
            _l2_real = _ilu.module_from_spec(_spec)
            sys.modules[_MOD_NAME] = _l2_real  # echten Namen registrieren → @dataclass OK
            _spec.loader.exec_module(_l2_real)
            import services as _svc

            _svc.layer2_routing = _l2_real
        else:
            _l2_real = _existing

        # Mapping-Konstante prüfen (schnell, kein DB nötig)
        assert hasattr(_l2_real, "_ROUTED_TO_MAP"), "_ROUTED_TO_MAP fehlt im echten Modul"
        assert _l2_real._ROUTED_TO_MAP.get("voice_feedback_api") == "voice_feedback"

        # Außerdem: persist_routing_decision schreibt den gemappten Wert
        written_vals = []
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)

        def capture_execute(sql, params):
            written_vals.append(params.get("rt"))

        mock_db.execute.side_effect = capture_execute

        decision = types.SimpleNamespace(target="voice_feedback_api")

        with patch.object(_l2_real, "sync_session_factory", return_value=mock_db):
            _l2_real.persist_routing_decision("log-map-1", decision)

        assert written_vals == [
            "voice_feedback"
        ], f"Erwartet 'voice_feedback', bekommen {written_vals}"
