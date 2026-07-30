"""Tier 1 — Ausstieg aus einem laufenden Gespräch (C5).

Sobald eine `bot_session` (mode 'random_smart' oder 'targeted') aktiv ist, wird
jede eingehende Nachricht als Antwort auf die gestellte Frage geroutet
(`tasks/telegram_task.py:_load_active_session` → p08). Sessions haben kein TTL.
Wer also am Montagmorgen die proaktive Frage nicht beantworten will, hat keinen
Ausgang: alles, was er danach schickt, verschwindet im Interview.

⚠️ ZUSCHNITT: Der Plan schrieb `_onboarding_cancel` für den getippten Wizard. Den
gibt es seit der Doktrin-Entfernung nicht mehr — `api/telegram.py` enthält kein
bot_session mehr. Übrig bleibt (und darum geht es hier) der Ausstieg aus den
random_smart-/targeted-Interviews.

⚠️ STATUS 'expired', NICHT 'closed'. Zwei Gründe:
  1. `tasks/session_post_task.py:200` überspringt alles mit status != 'closed'.
     Ein abgebrochenes Interview als 'closed' zu markieren, würde die
     Post-Generierung scharf stellen — der Tester bricht ab und bekommt trotzdem
     einen Post aus halben Antworten.
  2. Die CHECK-Constraint erlaubt nur ('active','closed','expired')
     (`alembic/versions/019_telegram_tables.py:99`), und `deploy.yml` fährt KEIN
     `alembic upgrade head` — ein neuer Wert wäre auf dem Server tote Migration.

NIE `from api import telegram` benutzen — Geschwister-Stub vergiftet sys.modules.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@localhost/t")
os.environ.setdefault("SYNC_DATABASE_URL", "postgresql://t:t@localhost/t")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DEFAULT_TENANT_KEY", "test-key-32-chars-padded-xxxxxxx")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")

import importlib.util as _ilu
import sys
from unittest.mock import MagicMock, patch

_BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
# api.telegram beschaffen — zwei Fallen auf einmal:
#   1. Ein bereits geladenes ECHTES Modul darf NICHT ersetzt werden. pytest
#      importiert beim Collect alle Testdateien; tauscht eine davon das Modulobjekt
#      weg, patcht eine Geschwisterdatei ihr altes Objekt, während der
#      Produktionscode `from api.telegram import ...` zur Laufzeit das neue auflöst
#      (kostete 2 Phantom-Failures in test_telegram_poller.py).
#   2. `_telegram_task_env.py` legt unter demselben Namen ein STUB-Modul ab. Wer das
#      blind wiederverwendet, testet gegen ein Modul ohne die zu prüfenden
#      Funktionen — das ging bisher nur gut, weil zufällig eine alphabetisch frühere
#      Datei das echte Modul lud.
# Also: echtes Modul wiederverwenden, Stub durch das echte ersetzen.
_existing = sys.modules.get("api.telegram")
if _existing is not None and hasattr(_existing, "_handle_callback_query"):
    tg = _existing
else:
    _at_spec = _ilu.spec_from_file_location(
        "api.telegram", os.path.join(_BACKEND, "api", "telegram.py")
    )
    tg = _ilu.module_from_spec(_at_spec)
    sys.modules["api.telegram"] = tg
    _at_spec.loader.exec_module(tg)

TENANT = "6cff9601-ce95-43c6-b928-5b13b90d4df3"
CHAT = 4711


def _session_db(rows=(("sess-1", None),)):
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    db.execute.return_value.fetchall.return_value = list(rows)
    return db


def _cancel(rows=(("sess-1", None),), db=None):
    """Ruft _cancel_active_session. Gibt (Rückgabewert, db-Mock, send-Mock) zurück.

    Zeilenform (id, topic_idea_id): das UPDATE gibt seit PR 2 beide Spalten zurück —
    abgebrochene targeted-Interviews geben ihre Ursprungsnachricht wieder frei.
    """
    db = db if db is not None else _session_db(rows)
    with (
        patch.object(tg, "sync_session_factory", return_value=db),
        patch.object(tg, "_send_telegram_message") as send,
    ):
        result = tg._cancel_active_session(TENANT, CHAT)
    return result, db, send


def _broken_db():
    db = MagicMock()
    db.__enter__ = MagicMock(side_effect=RuntimeError("db down"))
    db.__exit__ = MagicMock(return_value=False)
    return db


def _executed_sql(db) -> str:
    return " ".join(str(c.args[0]) for c in db.execute.call_args_list)


class TestCancelActiveSession:
    def test_running_interview_gets_cancelled(self):
        result, _, _ = _cancel()
        assert result is True

    def test_cancel_marks_expired_and_never_closed(self):
        """'closed' würde session_post_task scharf stellen (siehe Modul-Docstring)."""
        _, db, _ = _cancel()
        sql = _executed_sql(db)
        assert "UPDATE bot_session" in sql, "Session wird gar nicht beendet"
        assert "'expired'" in sql, "Abbruch setzt nicht den terminalen Status 'expired'"
        assert (
            "'closed'" not in sql
        ), "Abbruch setzt 'closed' — session_post_task würde daraus noch einen Post bauen"

    def test_cancel_is_tenant_scoped(self):
        """E3-Mandantentrennung: kein Abbruch fremder Sessions."""
        _, db, _ = _cancel()
        update_calls = [c for c in db.execute.call_args_list if "UPDATE" in str(c.args[0])]
        assert update_calls, "kein UPDATE abgesetzt"
        params = update_calls[-1].args[1]
        assert params.get("tid") == TENANT, f"UPDATE nicht tenant-gescopet: {params}"

    def test_cancel_only_touches_interview_sessions(self):
        _, db, _ = _cancel()
        sql = _executed_sql(db)
        assert (
            "random_smart" in sql and "targeted" in sql
        ), "Auswahl grenzt die Interview-Modi nicht ein"

    def test_user_gets_a_confirmation(self):
        _, _, send = _cancel()
        assert send.called, "Abbruch bleibt unbestätigt — Tester weiß nicht, ob er raus ist"
        assert "abgebrochen" in send.call_args.args[1].lower()

    def test_confirmation_shows_the_way_on(self):
        _, _, send = _cancel()
        assert "Sprachnachricht" in send.call_args.args[1] or "/help" in send.call_args.args[1]

    def test_no_session_is_answered_honestly(self):
        result, _, send = _cancel(rows=())
        assert result is False
        assert send.called, "Abbruch ohne laufendes Gespräch bleibt stumm"

    def test_db_error_fails_open(self):
        result, _, _ = _cancel(db=_broken_db())
        assert result is False, "DB-Fehler darf nicht durchschlagen"

    def test_db_error_still_answers_the_user(self):
        """Sonst drückt der Tester „Abbrechen", bekommt NICHTS, und sitzt weiter fest —
        genau der Zustand, den C5 auflösen soll."""
        _, _, send = _cancel(db=_broken_db())
        assert send.called, "Abbruch scheitert stumm — keine Rückmeldung an den Tester"

    def test_every_active_interview_is_ended_not_just_the_newest(self):
        """Zwei Taps auf der noch sichtbaren Ideenliste erzeugen ZWEI aktive Sessions
        (p08_opener prüft nicht auf laufende). Beendet man nur die neueste, findet
        _load_active_session die ältere und schluckt die nächste Nachricht weiter —
        während der Bot „ich frage nicht weiter" behauptet hat."""
        _, db, _ = _cancel(rows=(("sess-1", None), ("sess-2", None)))
        update_sql = " ".join(
            str(c.args[0]) for c in db.execute.call_args_list if "UPDATE" in str(c.args[0])
        )
        assert (
            "LIMIT" not in update_sql.upper()
        ), "Abbruch beendet nur EINE Session — ältere bleiben aktiv und fangen weiter ab"


class TestCancelCommandReachesEveryEntryPath:
    """`_try_memory_command` wird von telegram_webhook UND dispatch_inbound_update
    aufgerufen — deshalb sitzt der Ausstieg dort und nicht im Dispatch."""

    def _run(self, command):
        with (
            patch.object(tg, "_cancel_active_session") as cancel,
            patch.object(tg, "_send_telegram_message"),
        ):
            handled = tg._try_memory_command(TENANT, CHAT, command)
        return handled, cancel

    def test_abbrechen_is_recognised(self):
        handled, cancel = self._run("/abbrechen")
        assert handled is True, "/abbrechen läuft weiter in den Unbekanntes-Kommando-Zweig"
        cancel.assert_called_once_with(TENANT, CHAT)

    def test_cancel_alias(self):
        handled, cancel = self._run("/cancel")
        assert handled is True and cancel.called

    def test_stop_alias(self):
        handled, cancel = self._run("/stop")
        assert handled is True and cancel.called

    def test_unrelated_command_is_untouched(self):
        handled, cancel = self._run("/gibtsnicht")
        assert handled is False and not cancel.called


class TestCancelInThePollingPath:
    def _dispatch(self, text_content):
        update = {
            "update_id": 7,
            "message": {"chat": {"id": CHAT}, "from": {"id": 5}, "text": text_content},
        }
        with (
            patch.object(tg, "_cancel_active_session") as cancel,
            patch.object(tg, "_send_telegram_message") as send,
            patch.object(tg, "_store_and_dispatch") as store,
        ):
            tg.dispatch_inbound_update(update, TENANT)
        return cancel, send, store

    def test_cancel_word_reaches_the_handler(self):
        cancel, _, _ = self._dispatch("/abbrechen")
        cancel.assert_called_once_with(TENANT, CHAT)

    def test_cancel_word_is_not_called_an_unknown_command(self):
        _, send, _ = self._dispatch("/abbrechen")
        sent = " ".join(c.args[1] for c in send.call_args_list)
        assert "Unbekanntes Kommando" not in sent

    def test_cancel_word_is_not_swallowed_as_content(self):
        _, _, store = self._dispatch("/abbrechen")
        assert not store.called, "Abbruch-Kommando landet als Content im Gedächtnis"


class TestCancelButton:
    def test_button_cancels_the_session(self):
        callback = {
            "id": "cb-1",
            "data": "cmd:session_cancel",
            "from": {"id": 42},
            "message": {"chat": {"id": CHAT}},
        }
        with (
            patch.object(tg, "_cancel_active_session") as cancel,
            patch.object(tg, "_send_telegram_message"),
        ):
            tg._handle_callback_query(callback, known_tenant_id=TENANT)
        cancel.assert_called_once_with(TENANT, CHAT)


class TestInterviewCancelKeyboard:
    def test_keyboard_offers_the_cancel_callback(self):
        datas = [
            b["callback_data"]
            for row in tg._interview_cancel_keyboard()["inline_keyboard"]
            for b in row
        ]
        assert "cmd:session_cancel" in datas

    def test_each_call_returns_a_fresh_dict(self):
        """Ein geteiltes Modul-Dict könnte von einem Caller mutiert werden."""
        first = tg._interview_cancel_keyboard()
        first["inline_keyboard"].append([{"text": "x", "callback_data": "y"}])
        assert len(tg._interview_cancel_keyboard()["inline_keyboard"]) == 1


class TestEscapeHatchIsDiscoverable:
    def test_help_names_the_cancel_command(self):
        with patch.object(tg, "_send_telegram_message") as send:
            tg._try_memory_command(TENANT, CHAT, "/help")
        assert (
            "/abbrechen" in send.call_args.args[1]
        ), "/help nennt den Ausgang nicht — ein Ausgang, den keiner findet, ist keiner"
