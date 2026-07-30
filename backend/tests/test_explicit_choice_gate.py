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

import importlib.util as _ilu
import os
import sys
import types as _types
from unittest.mock import MagicMock, patch

from tests._telegram_task_env import active_session, make_guard_db_mock, tt

# `_telegram_task_env` legt für api.telegram einen Stub ohne `_choice_keyboard` ab.
# `_send_choice_prompt` importiert den Helfer lazy und fängt ImportError still —
# ohne echtes Modul liefe dieser Test grün ins Leere bzw. scheiterte mit einem
# irreführenden AttributeError auf dem Sender-Mock. Verlassen wir uns darauf, dass
# eine alphabetisch frühere Datei das echte Modul schon geladen hat, bricht der
# Test beim ersten Umbenennen. Also hier selbst sicherstellen.
_BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_existing_tg = sys.modules.get("api.telegram")
if _existing_tg is None or not hasattr(_existing_tg, "_choice_keyboard"):
    _tg_spec = _ilu.spec_from_file_location(
        "api.telegram", os.path.join(_BACKEND, "api", "telegram.py")
    )
    _tg_mod = _ilu.module_from_spec(_tg_spec)
    sys.modules["api.telegram"] = _tg_mod
    _tg_spec.loader.exec_module(_tg_mod)

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
        with (
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
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
        with (
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
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


# ---------------------------------------------------------------------------
# 4. Abgrenzungen, die im Code stimmen und ungeschützt waren
# ---------------------------------------------------------------------------


class TestChannelBoundary:
    @patch("tasks.telegram_task._route_inbound_message", return_value=None)
    @patch("tasks.telegram_task._awaits_user_choice", return_value=True)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_whatsapp_bekommt_keine_inline_buttons(self, mock_run, _store, _gate, mock_route):
        """Inline-Keyboards sind Telegram-spezifisch — der Adapter kennt sie nicht."""
        mock_run.return_value = "chunk-w"
        sender = MagicMock(return_value=True)
        with (
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
            result = tt._process_text(
                "log-wa",
                "tenant-1",
                {"text": "Ein Gedanke über WhatsApp geschickt.", "_channel": "whatsapp"},
            )

        assert result.get("routed_to") != "awaiting_user_choice"
        mock_route.assert_called_once()
        sender.assert_not_called()


_cih_spec = _ilu.spec_from_file_location(
    "chat_intent_heuristics_real_test",
    os.path.join(_BACKEND, "services", "chat_intent_heuristics.py"),
)
_cih_real = _ilu.module_from_spec(_cih_spec)
_cih_spec.loader.exec_module(_cih_real)


class TestAwaitsUserChoiceMitEchterHeuristik:
    """Mit der ECHTEN `is_idea_request` statt dem Stub aus `_telegram_task_env`.

    „Einfach nicht patchen" genügt hier nicht: die Stub-Umgebung ersetzt
    `services.chat_intent_heuristics` vollständig durch MagicMocks mit
    `return_value=False`. Ein Test ohne Patch prüfte also nicht die Regex, sondern
    einen Mock — grün, ohne irgendetwas zu belegen. Deshalb wird die echte Funktion
    explizit eingesetzt.
    """

    @patch("services.chat_intent_heuristics.is_idea_request", _cih_real.is_idea_request)
    @patch("tasks.telegram_task._is_pending_variant_choice", return_value=False)
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    def test_echte_ideen_anfrage_wird_erkannt(self, _sess, _pend):
        assert tt._awaits_user_choice("tenant-1", "gib mir Ideen für einen Post") is False

    @patch("services.chat_intent_heuristics.is_idea_request", _cih_real.is_idea_request)
    @patch("tasks.telegram_task._is_pending_variant_choice", return_value=False)
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    def test_echte_erzaehlung_wartet_auf_wahl(self, _sess, _pend):
        assert (
            tt._awaits_user_choice(
                "tenant-1", "Heute war ich bei einem Kunden und wir sprachen über Preise."
            )
            is True
        )


class TestChatIdFallback:
    """Fehlt „chat" im Payload, wäre die Nachricht sonst ohne jede Reaktion zu Ende.

    Genau der Zustand, den diese PR beseitigt — er darf nicht durch die Hintertür
    zurückkommen, nur weil ein Payload-Feld fehlt.
    """

    @patch("tasks.telegram_task._resolve_chat_id", return_value=999)
    @patch("tasks.telegram_task._route_inbound_message")
    @patch("tasks.telegram_task._awaits_user_choice", return_value=True)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_ohne_chat_im_payload_wird_der_tenant_chat_genutzt(
        self, mock_run, _store, _gate, _route, _resolve
    ):
        mock_run.return_value = "chunk-f"
        sender = MagicMock(return_value=True)
        with (
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
            result = tt._process_text(
                "log-f1", "tenant-1", {"text": "Ein Gedanke ohne chat-Schlüssel im Payload."}
            )

        assert sender.call_args.args[0] == 999
        assert result["choice_prompt_sent"] is True

    @patch("tasks.telegram_task._resolve_chat_id", return_value=None)
    @patch("tasks.telegram_task._route_inbound_message")
    @patch("tasks.telegram_task._awaits_user_choice", return_value=True)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_kein_chat_auffindbar_wird_ehrlich_vermerkt(
        self, mock_run, _store, _gate, _route, _resolve
    ):
        """Kein erfundener Erfolg: das Ergebnis-Dict sagt, dass nichts ankam."""
        mock_run.return_value = "chunk-f2"
        sender = MagicMock(return_value=True)
        with (
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
            result = tt._process_text("log-f2", "tenant-1", {"text": "Ein Gedanke ins Leere."})

        sender.assert_not_called()
        assert result["choice_prompt_sent"] is False

    @patch("tasks.telegram_task._resolve_chat_id", return_value=999)
    @patch("tasks.telegram_task._route_inbound_message")
    @patch("tasks.telegram_task._awaits_user_choice", return_value=True)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_nicht_zugestellter_prompt_wird_nicht_als_erfolg_verbucht(
        self, mock_run, _store, _gate, _route, _resolve
    ):
        """_send_telegram_message WIRFT nicht, es gibt False zurück."""
        mock_run.return_value = "chunk-f3"
        sender = MagicMock(return_value=False)
        with (
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
            result = tt._process_text("log-f3", "tenant-1", {"text": "Telegram antwortet 429."})

        assert result["choice_prompt_sent"] is False
        assert result["routed_to"] == "awaiting_user_choice"
