"""Der Eingangs-Zug an beiden Eingaengen — Sprache und Text.

Spec: docs/superpowers/specs/2026-08-05-telegram-eingangs-zug-design.md §4, §10

Gate-Reihenfolge: Session → P13-Wahl → P09 → P14 → Buttons. Die ersten drei
liegen bereits in `_awaits_user_choice`; P14 laeuft nur, wenn die True sagt.

Anti-Pollution: geteilte Stub-Umgebung importieren, NIE `from tasks import
telegram_task` (vgl. tests/_telegram_task_env.py).
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import types as _types
from unittest.mock import MagicMock, patch

from tests._telegram_task_env import make_guard_db_mock, tt

# Wie in test_explicit_choice_gate.py: das ECHTE api.telegram sicherstellen,
# damit die Keyboards gegen die Wirklichkeit geprueft werden statt gegen Stubs.
# Gleiches Wächter-Attribut wie dort (_choice_keyboard): der Stub in
# _telegram_task_env.py traegt inzwischen auch _entry_keep_keyboard, ein
# hasattr-Check darauf wuerde also NIE auf das echte Modul umschalten.
_BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_existing_tg = sys.modules.get("api.telegram")
if _existing_tg is None or not hasattr(_existing_tg, "_choice_keyboard"):
    _tg_spec = _ilu.spec_from_file_location(
        "api.telegram", os.path.join(_BACKEND, "api", "telegram.py")
    )
    _tg_mod = _ilu.module_from_spec(_tg_spec)
    sys.modules["api.telegram"] = _tg_mod
    _tg_spec.loader.exec_module(_tg_mod)


def _entscheidung(handlung: str, antwort: str = ""):
    return _types.SimpleNamespace(handlung=handlung, antwort=antwort)


_ANWEISUNG = "Ich würde gerne einen LinkedIn-Post machen"
_ANWEISUNG_MIT_THEMA = "Ich würde gerne einen Post machen über mein Kundengespräch gestern"
_INHALT = "Ich hatte heute ein Gespräch mit einem Kunden, das mich beschäftigt hat."


# ---------------------------------------------------------------------------
# 1. Text-Eingang
# ---------------------------------------------------------------------------


class TestTextEingang:
    def _lauf(self, payload, entscheidung, sender, log_id="log-p14"):
        with (
            patch("services.p14_entry_service.p14_entry", return_value=entscheidung),
            patch("services.p08_service.erzeuge_bot_session", return_value="sess-9"),
            patch("tasks.telegram_task._markiere_chunk_als_anweisung", return_value=True),
            patch("tasks.telegram_task._awaits_user_choice", return_value=True),
            patch("tasks.telegram_task.asyncio.run", return_value="chunk-1"),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
            return tt._process_text(log_id, "tenant-1", payload)

    def test_anweisung_startet_ein_gespraech_ohne_buttons(self):
        """Abnahmekriterium 1: eine Frage, eine Session, KEINE Buttons."""
        sender = MagicMock(return_value=True)
        result = self._lauf(
            {"text": _ANWEISUNG, "chat": {"id": 42}},
            _entscheidung("gespraech", "Worum ging es zuletzt?"),
            sender,
        )

        assert result["routed_to"] == "p14_gespraech"
        assert result["bot_session_id"] == "sess-9"
        assert result["p14_message_sent"] is True
        assert sender.call_args.args[1] == "Worum ging es zuletzt?"
        datas = [
            b["callback_data"]
            for row in sender.call_args.kwargs["reply_markup"]["inline_keyboard"]
            for b in row
        ]
        assert datas == ["cmd:entry_keep"], "an der Eroeffnung haengt der Ausstieg, nicht die Wahl"

    def test_session_wird_als_targeted_ohne_idee_angelegt(self):
        """Spec §6: mode='targeted', topic_idea_id=NULL — keine Migration."""
        sender = MagicMock(return_value=True)
        anleger = MagicMock(return_value="sess-9")
        with (
            patch(
                "services.p14_entry_service.p14_entry",
                return_value=_entscheidung("gespraech", "Und dann?"),
            ),
            patch("services.p08_service.erzeuge_bot_session", anleger),
            patch("tasks.telegram_task._markiere_chunk_als_anweisung", return_value=True),
            patch("tasks.telegram_task._awaits_user_choice", return_value=True),
            patch("tasks.telegram_task.asyncio.run", return_value="chunk-1"),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
            tt._process_text("log-p14b", "tenant-1", {"text": _ANWEISUNG, "chat": {"id": 42}})

        kw = anleger.call_args.kwargs
        assert kw["mode"] == "targeted"
        assert kw["topic_idea_id"] is None
        assert kw["frage"] == "Und dann?"
        assert kw["tenant_id"] == "tenant-1"

    def test_erkannte_anweisung_erzeugt_keine_content_idea(self):
        """Abnahmekriterium 6. Der [✍️]-Weg legt eine an, P14 braucht das nicht."""
        sender = MagicMock(return_value=True)
        idee = MagicMock(return_value="idea-1")
        with patch("tasks.p13_variants_task._create_manual_idea", idee):
            self._lauf(
                {"text": _ANWEISUNG, "chat": {"id": 42}},
                _entscheidung("gespraech", "Worum ging es?"),
                sender,
            )
        idee.assert_not_called()

    def test_inhalt_bekommt_die_zwei_buttons_wie_heute(self):
        """Abnahmekriterium 3 — die Doktrin vom 30.07. bleibt vollstaendig."""
        sender = MagicMock(return_value=True)
        result = self._lauf(
            {"text": _INHALT, "chat": {"id": 42}}, _entscheidung("ablegen"), sender, "log-p14c"
        )

        assert result["routed_to"] == "awaiting_user_choice"
        datas = [
            b["callback_data"]
            for row in sender.call_args.kwargs["reply_markup"]["inline_keyboard"]
            for b in row
        ]
        assert datas == ["cmd:msg_post:log-p14c", "cmd:msg_keep:log-p14c"]


# ---------------------------------------------------------------------------
# 2. Voice-Eingang — dieselbe Reihenfolge, derselbe Ausgang
# ---------------------------------------------------------------------------


class TestVoiceEingang:
    def _lauf(self, transkript, entscheidung, sender):
        with (
            patch("tasks.telegram_task._telegram_get_file", return_value=b"audio"),
            patch(
                "tasks.telegram_task.transcribe_voice",
                return_value=_types.SimpleNamespace(
                    text=transkript, model_id="voxtral", confidence=0.9
                ),
            ),
            patch("tasks.telegram_task._update_log_transcript"),
            patch("services.p14_entry_service.p14_entry", return_value=entscheidung),
            patch("services.p08_service.erzeuge_bot_session", return_value="sess-v"),
            patch("tasks.telegram_task._markiere_chunk_als_anweisung", return_value=True),
            patch("tasks.telegram_task._awaits_user_choice", return_value=True),
            patch("tasks.telegram_task.asyncio.run", return_value="chunk-v"),
            patch("api.telegram._send_telegram_message", sender),
        ):
            return tt._process_voice(
                "log-v1",
                "tenant-1",
                {"voice": {"file_id": "f1", "duration": 4}, "chat": {"id": 42}},
            )

    def test_gesprochene_anweisung_startet_ein_gespraech(self):
        """Abnahmekriterium 1 gilt fuer Sprache UND Text."""
        sender = MagicMock(return_value=True)
        result = self._lauf(_ANWEISUNG, _entscheidung("gespraech", "Worum geht's?"), sender)

        assert result["routed_to"] == "p14_gespraech"
        assert result["bot_session_id"] == "sess-v"
        assert "Notiert" not in sender.call_args.args[1], "kein 🎤-Notiert vor der Frage"

    def test_gesprochener_inhalt_bekommt_die_buttons(self):
        sender = MagicMock(return_value=True)
        result = self._lauf(_INHALT, _entscheidung("ablegen"), sender)

        assert result["routed_to"] == "awaiting_user_choice"
        assert "🎤" in sender.call_args.args[1]


# ---------------------------------------------------------------------------
# 3. Spec §5 — jeder Fehlerfall endet bei den Buttons, nie in Stille
# ---------------------------------------------------------------------------


class TestAusfallrichtung:
    def test_p14_wirft_faellt_auf_buttons(self):
        sender = MagicMock(return_value=True)
        with (
            patch("services.p14_entry_service.p14_entry", side_effect=RuntimeError("boom")),
            patch("tasks.telegram_task._awaits_user_choice", return_value=True),
            patch("tasks.telegram_task.asyncio.run", return_value="chunk-e1"),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
            result = tt._process_text(
                "log-e1", "tenant-1", {"text": _ANWEISUNG, "chat": {"id": 42}}
            )
        assert result["routed_to"] == "awaiting_user_choice"
        assert result["choice_prompt_sent"] is True

    def test_session_anlage_scheitert_faellt_auf_buttons_ohne_halbe_session(self):
        """Spec §5, letzte Zeile: 'ablegen, ohne halbe Session'."""
        sender = MagicMock(return_value=True)
        with (
            patch(
                "services.p14_entry_service.p14_entry",
                return_value=_entscheidung("gespraech", "Worum?"),
            ),
            patch("services.p08_service.erzeuge_bot_session", side_effect=RuntimeError("db weg")),
            patch("tasks.telegram_task._awaits_user_choice", return_value=True),
            patch("tasks.telegram_task.asyncio.run", return_value="chunk-e2"),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
            result = tt._process_text(
                "log-e2", "tenant-1", {"text": _ANWEISUNG, "chat": {"id": 42}}
            )
        assert result["routed_to"] == "awaiting_user_choice"
        # Die Eroeffnungsfrage darf NICHT rausgegangen sein.
        gesendete_texte = [c.args[1] for c in sender.call_args_list]
        assert not any(t == "Worum?" for t in gesendete_texte)

    def test_send_scheitert_verwirft_die_session_und_faellt_auf_buttons(self):
        """Ohne Rollback bliebe eine unsichtbare Session zurueck, die jede
        weitere Nachricht als Interview-Antwort schluckt."""
        sender = MagicMock(return_value=False)  # _send_telegram_message wirft nicht, es gibt False
        verwerfer = MagicMock()
        with (
            patch(
                "services.p14_entry_service.p14_entry",
                return_value=_entscheidung("gespraech", "Worum?"),
            ),
            patch("services.p08_service.erzeuge_bot_session", return_value="sess-tot"),
            patch("tasks.telegram_task._verwerfe_session", verwerfer),
            patch("tasks.telegram_task._awaits_user_choice", return_value=True),
            patch("tasks.telegram_task.asyncio.run", return_value="chunk-e3"),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
            result = tt._process_text(
                "log-e3", "tenant-1", {"text": _ANWEISUNG, "chat": {"id": 42}}
            )
        verwerfer.assert_called_once_with("sess-tot")
        assert result["routed_to"] == "awaiting_user_choice"

    def test_ohne_auffindbaren_chat_entsteht_keine_session(self):
        anleger = MagicMock(return_value="sess-x")
        with (
            patch(
                "services.p14_entry_service.p14_entry",
                return_value=_entscheidung("gespraech", "Worum?"),
            ),
            patch("services.p08_service.erzeuge_bot_session", anleger),
            patch("tasks.telegram_task._resolve_chat_id", return_value=None),
            patch("tasks.telegram_task._awaits_user_choice", return_value=True),
            patch("tasks.telegram_task.asyncio.run", return_value="chunk-e4"),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", MagicMock(return_value=True)),
        ):
            result = tt._process_text("log-e4", "tenant-1", {"text": _ANWEISUNG})
        anleger.assert_not_called()
        assert result["routed_to"] == "awaiting_user_choice"

    def test_soft_time_limit_reisst_den_task_ab_statt_weiterzulaufen(self):
        """Muster von telegram_task.py:713 — die weiche Grenze muss nach oben."""
        import pytest
        from celery.exceptions import SoftTimeLimitExceeded

        with (
            patch("services.p14_entry_service.p14_entry", side_effect=SoftTimeLimitExceeded()),
            patch("tasks.telegram_task._awaits_user_choice", return_value=True),
            patch("tasks.telegram_task.asyncio.run", return_value="chunk-stl"),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", MagicMock(return_value=True)),
        ):
            with pytest.raises(SoftTimeLimitExceeded):
                tt._process_text("log-stl", "tenant-1", {"text": _ANWEISUNG, "chat": {"id": 42}})


# ---------------------------------------------------------------------------
# 4. Die Reihenfolge — P09 steht VOR P14
# ---------------------------------------------------------------------------


_cih_spec = _ilu.spec_from_file_location(
    "chat_intent_heuristics_real_p14_test",
    os.path.join(_BACKEND, "services", "chat_intent_heuristics.py"),
)
_cih_real = _ilu.module_from_spec(_cih_spec)
_cih_spec.loader.exec_module(_cih_real)


class TestGateReihenfolge:
    """Abnahmekriterium 4: 'Gib mir Ideen für einen Post' → P09, P14 kommt nicht zum Zug.

    „gib mir Ideen" ist eine etablierte, deterministisch erkannte Bedeutung, die
    kein Modell neu verhandeln soll.
    """

    @patch("services.chat_intent_heuristics.is_idea_request", _cih_real.is_idea_request)
    @patch("tasks.telegram_task._is_pending_variant_choice", return_value=False)
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    def test_ideen_anfrage_erreicht_p14_gar_nicht(self, _sess, _pend):
        p14 = MagicMock()
        with (
            patch("services.p14_entry_service.p14_entry", p14),
            patch("tasks.telegram_task._route_inbound_message", return_value=None),
            patch("tasks.telegram_task.asyncio.run", return_value="chunk-p09"),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", MagicMock(return_value=True)),
        ):
            tt._process_text(
                "log-p09", "tenant-1", {"text": "gib mir Ideen für einen Post", "chat": {"id": 42}}
            )
        p14.assert_not_called()

    @patch("tasks.telegram_task._is_pending_variant_choice", return_value=False)
    @patch("services.chat_intent_heuristics.is_idea_request", return_value=False)
    @patch("tasks.telegram_task._load_active_session")
    def test_laufendes_gespraech_erreicht_p14_gar_nicht(self, mock_sess, _idea, _pend):
        mock_sess.return_value = _types.SimpleNamespace(id="sess-1", status="active")
        p14 = MagicMock()
        with (
            patch("services.p14_entry_service.p14_entry", p14),
            patch("tasks.telegram_task._route_inbound_message", return_value=None),
            patch("tasks.telegram_task.asyncio.run", return_value="chunk-sess"),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", MagicMock(return_value=True)),
        ):
            tt._process_text(
                "log-sess", "tenant-1", {"text": "Ja, genau so war das.", "chat": {"id": 42}}
            )
        p14.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Der Memory-Chunk (Spec §7)
# ---------------------------------------------------------------------------


class TestChunkMarkierung:
    def _db_mock(self):
        db = MagicMock()
        db.__enter__ = MagicMock(return_value=db)
        db.__exit__ = MagicMock(return_value=False)
        return db

    def test_markiert_ueber_source_ref_nicht_ueber_die_chunk_id(self):
        """_store_chunk_async gibt nur die ID des ERSTEN Chunks zurueck. Ein
        laengerer Text wird gechunkt — die uebrigen blieben unmarkiert."""
        db = self._db_mock()
        with patch.object(tt, "sync_session_factory", return_value=db):
            assert tt._markiere_chunk_als_anweisung("tenant-1", "log-55") is True

        sql = str(db.execute.call_args.args[0])
        params = db.execute.call_args.args[1]
        assert "memory_chunks" in sql
        assert "source_ref" in sql
        assert params["ref"] == "telegram_message_log:log-55"
        assert params["tid"] == "tenant-1"
        db.commit.assert_called_once()

    def test_schreibt_in_metadata_nicht_in_classification(self):
        """classification ist besetzt: store_chunk(classify=True) vergibt dort
        eine inhaltliche Kategorie, die values_backfill_task auswertet. Ein
        Steuerungsmerkmal gehoert nicht in dieses Vokabular."""
        db = self._db_mock()
        with patch.object(tt, "sync_session_factory", return_value=db):
            tt._markiere_chunk_als_anweisung("tenant-1", "log-56")

        sql = str(db.execute.call_args.args[0])
        params = db.execute.call_args.args[1]
        assert "metadata" in sql
        assert "classification" not in sql
        assert '"intent"' in params["patch"]
        assert "start_instruction" in params["patch"]

    def test_fehler_verhindert_kein_gespraech(self):
        """Fail-open: ein Markierungsfehler darf nie ein Gespraech verhindern."""
        with patch.object(tt, "sync_session_factory", side_effect=RuntimeError("db weg")):
            assert tt._markiere_chunk_als_anweisung("tenant-1", "log-57") is False

    def test_gespraechsstart_laeuft_trotz_markierungsfehler_durch(self):
        sender = MagicMock(return_value=True)
        with (
            patch(
                "services.p14_entry_service.p14_entry",
                return_value=_entscheidung("gespraech", "Worum?"),
            ),
            patch("services.p08_service.erzeuge_bot_session", return_value="sess-m"),
            patch(
                "tasks.telegram_task._markiere_chunk_als_anweisung",
                side_effect=RuntimeError("darf nicht durchschlagen"),
            ),
            patch("tasks.telegram_task._awaits_user_choice", return_value=True),
            patch("tasks.telegram_task.asyncio.run", return_value="chunk-m"),
            patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)),
            patch("api.telegram._send_telegram_message", sender),
        ):
            result = tt._process_text("log-m", "tenant-1", {"text": _ANWEISUNG, "chat": {"id": 42}})
        assert result["routed_to"] == "p14_gespraech"
