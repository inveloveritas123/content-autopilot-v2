"""PR 2 — die Weiche: entscheidet der Nutzer, oder greift ein bestehender Pfad?

Der Bot rät nicht mehr per LLM, was jemand wollte. Nur wenn ein bestehender Pfad
die Nachricht nachweislich erwartet — laufendes Interview, Ideen-Anfrage, echte
Varianten-Wahl — bleibt es beim alten Verhalten. Sonst fragt er nach.

Warum das nötig war: der LLM-Rateschritt endete an vier belegten Stellen in Stille
(kein Consumer für help_response/close_friendly, `flagged_for_review` schlägt jeden
korrekten Intent, INJECTION_PATTERNS trifft Alltagsdeutsch, und ohne Session
erreicht eine Nachricht Layer1 nur über zwei Heuristiken).

Anti-Pollution: geteilte Stub-Umgebung importieren, NIE `from tasks import
telegram_task` (vgl. tests/_telegram_task_env.py).
"""

from __future__ import annotations

import types as _types
from unittest.mock import MagicMock, patch

from tests._telegram_task_env import active_session, make_guard_db_mock, tt

# ---------------------------------------------------------------------------
# 1. _awaits_user_choice — die Weiche selbst
# ---------------------------------------------------------------------------


class TestAwaitsUserChoice:
    @patch("tasks.telegram_task._is_pending_variant_choice", return_value=False)
    @patch("services.chat_intent_heuristics.is_idea_request", return_value=False)
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    def test_ohne_gespraech_wartet_auf_wahl(self, _sess, _idea, _pend):
        assert tt._awaits_user_choice("tenant-1", "Heute war ein guter Tag im Büro.") is True

    @patch("tasks.telegram_task._is_pending_variant_choice", return_value=False)
    @patch("services.chat_intent_heuristics.is_idea_request", return_value=False)
    @patch("tasks.telegram_task._load_active_session")
    def test_aktive_session_keine_wahl(self, mock_sess, _idea, _pend):
        """Im Interview ist die Antwort eine Antwort — Buttons wären ein Fremdkörper."""
        mock_sess.return_value = active_session()
        assert tt._awaits_user_choice("tenant-1", "Ja, genau so war das.") is False

    @patch("tasks.telegram_task._is_pending_variant_choice", return_value=False)
    @patch("services.chat_intent_heuristics.is_idea_request", return_value=True)
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    def test_ideen_anfrage_keine_wahl(self, _sess, _idea, _pend):
        """Die Regex-Heuristik bleibt aktiv — sie ist deterministisch, kein LLM."""
        assert tt._awaits_user_choice("tenant-1", "gib mir mal ein paar Post-Ideen") is False

    @patch("tasks.telegram_task._is_pending_variant_choice", return_value=True)
    @patch("services.chat_intent_heuristics.is_idea_request", return_value=False)
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    def test_echte_variantenwahl_keine_wahl(self, _sess, _idea, _pend):
        assert tt._awaits_user_choice("tenant-1", "2") is False

    @patch("services.chat_intent_heuristics.is_idea_request", side_effect=RuntimeError("boom"))
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    def test_fehler_faellt_auf_heutiges_verhalten_zurueck(self, _sess, _idea):
        """Fail-open zu False: im Zweifel alter Pfad, nie ein Absturz des Chunk-Returns."""
        assert tt._awaits_user_choice("tenant-1", "irgendwas") is False


# ---------------------------------------------------------------------------
# 2. _is_pending_variant_choice — Marker UND Token, nie nur eins
# ---------------------------------------------------------------------------


class TestIsPendingVariantChoice:
    @patch("tasks.p13_variants_task._load_pending_idea", return_value={"idea_id": "i1"})
    @patch("tasks.p13_variants_task._parse_choice_token", return_value=2)
    def test_marker_und_token_ist_wahl(self, _tok, _pend):
        assert tt._is_pending_variant_choice("tenant-1", "2") is True

    @patch("tasks.p13_variants_task._load_pending_idea", return_value={"idea_id": "i1"})
    @patch("tasks.p13_variants_task._parse_choice_token", return_value=None)
    def test_veralteter_marker_ohne_token_ist_keine_wahl(self, _tok, mock_pend):
        """Der Fehler, der den LLM-Pfad wieder geöffnet hätte.

        Der Marker lebt 24 h. Ein Marker-only-Check hätte die Weiche gekippt und
        damit ausgerechnet das Raten reaktiviert, das diese PR abschaltet.
        Nebenbei belegt der Test die Reihenfolge: Regex zuerst, DB nur bei Bedarf.
        """
        assert tt._is_pending_variant_choice("tenant-1", "Ein langer Satz ohne Wahl") is False
        mock_pend.assert_not_called()

    @patch("tasks.p13_variants_task._load_pending_idea", return_value=None)
    @patch("tasks.p13_variants_task._parse_choice_token", return_value=2)
    def test_token_ohne_marker_ist_keine_wahl(self, _tok, _pend):
        assert tt._is_pending_variant_choice("tenant-1", "2") is False

    @patch("tasks.p13_variants_task._parse_choice_token", side_effect=RuntimeError("boom"))
    def test_fehler_ist_keine_wahl(self, _tok):
        assert tt._is_pending_variant_choice("tenant-1", "2") is False


# ---------------------------------------------------------------------------
# 3. Beide Task-Pfade — Prompt statt Routing
# ---------------------------------------------------------------------------


class TestProcessTextSendsChoice:
    @patch("tasks.telegram_task._route_inbound_message")
    @patch("tasks.telegram_task._awaits_user_choice", return_value=True)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_ohne_gespraech_sendet_buttons_und_routet_nicht(
        self, mock_run, _store, _gate, mock_route
    ):
        mock_run.return_value = "chunk-1"
        sender = MagicMock(return_value=True)
        with patch.object(
            tt, "sync_session_factory", return_value=make_guard_db_mock(None)
        ), patch("api.telegram._send_telegram_message", sender):
            result = tt._process_text(
                "log-77",
                "tenant-1",
                {"text": "Heute im Kundengespräch ist mir was aufgefallen.", "chat": {"id": 42}},
            )

        assert result["routed_to"] == "awaiting_user_choice"
        assert not mock_route.called, "der LLM-Rateschritt darf gar nicht erst laufen"
        markup = sender.call_args.kwargs["reply_markup"]
        datas = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
        assert datas == ["cmd:msg_post:log-77", "cmd:msg_keep:log-77"]
        assert "📝" in sender.call_args.args[1]

    @patch("tasks.telegram_task._route_inbound_message", return_value=None)
    @patch("tasks.telegram_task._awaits_user_choice", return_value=False)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_mit_gespraech_bleibt_beim_alten_pfad(self, mock_run, _store, _gate, mock_route):
        mock_run.return_value = "chunk-2"
        sender = MagicMock(return_value=True)
        with patch.object(
            tt, "sync_session_factory", return_value=make_guard_db_mock(None)
        ), patch("api.telegram._send_telegram_message", sender):
            result = tt._process_text(
                "log-78", "tenant-1", {"text": "Ja, so war das ungefähr.", "chat": {"id": 42}}
            )

        assert result.get("routed_to") != "awaiting_user_choice"
        mock_route.assert_called_once()
        assert sender.call_args.kwargs.get("reply_markup") is None


class TestProcessVoiceSendsChoice:
    @patch("tasks.telegram_task._route_inbound_message")
    @patch("tasks.telegram_task._awaits_user_choice", return_value=True)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    @patch("tasks.telegram_task._update_log_transcript")
    @patch("tasks.telegram_task.transcribe_voice")
    @patch("tasks.telegram_task._telegram_get_file", return_value=b"audio")
    def test_ohne_gespraech_sendet_buttons_und_routet_nicht(
        self, _get, mock_tx, _upd, mock_run, _store, _gate, mock_route
    ):
        mock_tx.return_value = _types.SimpleNamespace(
            text="Mir ist heute etwas zu Preisgesprächen eingefallen.",
            model_id="whisper",
            confidence=0.9,
        )
        mock_run.return_value = "chunk-3"
        sender = MagicMock(return_value=True)
        with patch("api.telegram._send_telegram_message", sender):
            result = tt._process_voice(
                "log-79",
                "tenant-1",
                {"voice": {"file_id": "f1", "duration": 5}, "chat": {"id": 42}},
            )

        assert result["routed_to"] == "awaiting_user_choice"
        mock_route.assert_not_called()
        datas = [
            b["callback_data"]
            for row in sender.call_args.kwargs["reply_markup"]["inline_keyboard"]
            for b in row
        ]
        assert datas == ["cmd:msg_post:log-79", "cmd:msg_keep:log-79"]
        assert "🎤" in sender.call_args.args[1]

    @patch("tasks.telegram_task._route_inbound_message", return_value=None)
    @patch("tasks.telegram_task._awaits_user_choice", return_value=False)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    @patch("tasks.telegram_task._update_log_transcript")
    @patch("tasks.telegram_task.transcribe_voice")
    @patch("tasks.telegram_task._telegram_get_file", return_value=b"audio")
    def test_mit_gespraech_bleibt_beim_alten_pfad(
        self, _get, mock_tx, _upd, mock_run, _store, _gate, mock_route
    ):
        mock_tx.return_value = _types.SimpleNamespace(
            text="Ja, das war ungefähr vor zwei Wochen.", model_id="whisper", confidence=0.9
        )
        mock_run.return_value = "chunk-4"
        sender = MagicMock(return_value=True)
        with patch("api.telegram._send_telegram_message", sender):
            result = tt._process_voice(
                "log-80",
                "tenant-1",
                {"voice": {"file_id": "f1", "duration": 5}, "chat": {"id": 42}},
            )

        assert result.get("routed_to") != "awaiting_user_choice"
        mock_route.assert_called_once()
        assert sender.call_args.kwargs.get("reply_markup") is None
