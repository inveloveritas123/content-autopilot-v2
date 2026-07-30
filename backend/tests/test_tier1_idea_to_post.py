"""Tier 1 — „✍️ Idee ausarbeiten" muss zu einem Post führen (C7).

Der Button versprach einen Post-Entwurf, löste aber `deliver_ideas_to_chat` aus —
den Task, der Ideen *auflistet*. Der Tester wählte also eine Idee und bekam die
Ideenliste erneut. Kein Entwurf, keine Frage, keine Fehlermeldung.

Der Kernpfad zum Post ist strukturell an eine `bot_session` gebunden: erst deren
Schließen fährt P12→P12b und liefert den Entwurf mit Freigabe-Buttons. „Idee
ausarbeiten" muss deshalb genau das tun, was die Wahl eines P13-Hooks tut —
`_start_targeted_session` aufrufen und das Interview eröffnen. Eine Abkürzung
„Post direkt generieren" gibt es nicht, sie würde den Pfad umgehen.

⚠️ `_start_targeted_session` fängt intern ALLES ab und gibt bei Fehlern `None`
zurück statt zu werfen. Ein reines try/except sähe den Fehlschlag nie — der
Rückgabewert ist das Signal.

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
import types
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
IDEA = "idea-42"


def _idea_db(row):
    """DB-Mock für den SELECT title, hook_suggestion in _brainstorming_pick_idea."""
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    db.execute.return_value.fetchone.return_value = row
    return db


_STARTED = {"session_id": "s1", "question_text": "Was war der Auslöser?"}


def _pick(row=("Wie wir Kunden onboarden", "Der erste Tag entscheidet"), started=_STARTED):
    """Klickt „Idee ausarbeiten" mit gestubbten Nachbarmodulen.

    Gibt (p13-Stub, p09-Stub, send-Mock) zurück. `started=None` simuliert den
    Fehlschlag von _start_targeted_session (es wirft nie, es gibt None zurück).
    """
    p13 = types.ModuleType("tasks.p13_variants_task")
    p13._start_targeted_session = MagicMock(return_value=started)
    p09 = types.ModuleType("tasks.p09_chat_ideas_task")
    p09.deliver_ideas_to_chat = MagicMock()

    with (
        patch.object(tg, "sync_session_factory", return_value=_idea_db(row)),
        patch.object(tg, "_send_telegram_message") as send,
        patch.dict(
            sys.modules,
            {"tasks.p13_variants_task": p13, "tasks.p09_chat_ideas_task": p09},
        ),
    ):
        tg._brainstorming_pick_idea(TENANT, CHAT, IDEA)
    return p13, p09, send


class TestPickIdeaStartsTheRealInterview:
    def test_chosen_idea_reaches_the_interview_starter(self):
        p13, _, _ = _pick()
        p13._start_targeted_session.assert_called_once_with(TENANT, IDEA)

    def test_pick_does_not_relist_ideas(self):
        _, p09, _ = _pick()
        assert (
            not p09.deliver_ideas_to_chat.delay.called
        ), "Idee-Wahl löst weiter die Ideen-LISTE aus statt den Post-Pfad"

    def test_user_is_told_that_questions_come_next(self):
        _, _, send = _pick()
        text = " ".join(c.args[1] for c in send.call_args_list)
        assert "Frage" in text, "Tester erfährt nicht, dass jetzt ein Interview startet"

    def test_ack_does_not_promise_an_immediate_draft(self):
        _, _, send = _pick()
        text = " ".join(c.args[1] for c in send.call_args_list)
        assert (
            "Einen Moment bitte" not in text
        ), "Ack verspricht weiter einen sofortigen Entwurf — es folgen aber erst Fragen"


class TestPickIdeaFailurePaths:
    def test_missing_idea_notifies(self):
        _, _, send = _pick(row=None)
        assert "nicht gefunden" in send.call_args.args[1].lower()

    def test_missing_idea_starts_no_session(self):
        p13, _, _ = _pick(row=None)
        assert not p13._start_targeted_session.called

    def test_failed_start_is_not_silent(self):
        """_start_targeted_session schluckt Fehler und gibt None zurück."""
        _, _, send = _pick(started=None)
        text = " ".join(c.args[1] for c in send.call_args_list).lower()
        assert (
            "nicht geklappt" in text or "nochmal" in text
        ), "Fehlgeschlagener Start bleibt für den Tester unsichtbar"
