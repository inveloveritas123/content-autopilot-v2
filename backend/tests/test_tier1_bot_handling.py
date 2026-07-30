"""Tier 1 — Handhabung: der Bot soll sich für den Tester fertig anfühlen.

Zwei Defekte aus dem Voll-Reaudit (29.07.):

C12 — der /help-Text behauptete einen Rhythmus, den der Scheduler nicht fährt:
  „Proaktiver Dialog (Mo – Fr, 10 Uhr) / Jeden Werktagmorgen …", während der
  Produktions-Default `0 9 * * 1,4` ist (`services/random_smart_config.py:16`),
  also Montag und Donnerstag um 9:00. Ein Hilfetext, der die eigene Mechanik
  falsch beschreibt, ist schlimmer als keiner — der Tester wartet Dienstag
  vergeblich und hält den Bot für kaputt.

C8 — „🔄 Neue Ideen generieren" (`cmd:bs_generate`) wurde als Button gebaut, aber
  nie im Callback-Dispatch behandelt. Ein Tipp darauf tat nichts: kein Text,
  keine Aktion, keine Fehlermeldung.

NIE `from api import telegram` benutzen — Geschwister-Stub vergiftet sys.modules.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@localhost/t")
os.environ.setdefault("SYNC_DATABASE_URL", "postgresql://t:t@localhost/t")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DEFAULT_TENANT_KEY", "test-key-32-chars-padded-xxxxxxx")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")

import importlib.util as _ilu
import inspect
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


def _callback(data: str) -> dict:
    return {
        "id": "cb-test",
        "data": data,
        "from": {"id": 42},
        "message": {"chat": {"id": CHAT}},
    }


class TestHelpTextMatchesRealSchedule:
    """C12 — der Hilfetext darf keinen Rhythmus behaupten, den der Cron nicht fährt."""

    def _help_text(self) -> str:
        with patch.object(tg, "_send_telegram_message") as send:
            handled = tg._try_memory_command(TENANT, CHAT, "/help")
        assert handled is True
        return send.call_args.args[1]

    def test_help_does_not_claim_weekday_mornings(self):
        text = self._help_text()
        for luege in ("Mo – Fr", "Mo-Fr", "10 Uhr", "Werktagmorgen"):
            assert luege not in text, (
                f"/help behauptet weiter '{luege}' — der Default-Cron ist "
                f"'0 9 * * 1,4' (Mo+Do, 9:00)"
            )

    def test_help_names_the_actual_default_days(self):
        text = self._help_text().lower()
        assert (
            "montag" in text and "donnerstag" in text
        ), "/help nennt die echten Tage des Default-Cron nicht"


class TestGenerateIdeasButtonWorks:
    """C8 — der Button war gebaut, aber nirgends behandelt: Tipp = nichts."""

    def _press(self):
        fake_task = MagicMock()
        fake_mod = types.ModuleType("tasks.p09_chat_ideas_task")
        fake_mod.deliver_ideas_to_chat = fake_task
        with patch.dict(sys.modules, {"tasks.p09_chat_ideas_task": fake_mod}):
            with patch.object(tg, "_send_telegram_message") as send:
                tg._handle_callback_query(_callback("cmd:bs_generate"), known_tenant_id=TENANT)
        return fake_task, send

    def test_button_dispatches_idea_generation(self):
        fake_task, _ = self._press()
        assert (
            fake_task.delay.called
        ), "'Neue Ideen generieren' löst keine Generierung aus — toter Button"
        assert (
            fake_task.delay.call_args.kwargs.get("tenant_id") == TENANT
        ), "Generierung läuft nicht tenant-scoped"

    def test_button_confirms_to_the_user(self):
        _, send = self._press()
        assert send.called, "Button antwortet dem Tester nicht — wirkt kaputt"

    def test_call_matches_the_real_task_signature(self):
        """Ein MagicMock akzeptiert JEDE Signatur — der echte Celery-Task nicht.

        celery prüft die Argumente bereits im Client (`strict_typing` ist Default),
        ein falscher Aufruf wirft also sofort TypeError, statt erst im Worker
        aufzuschlagen. Hier landete er im `except` des Handlers und der Tester bekam
        bei JEDEM Druck „Fehler beim Starten der Ideen-Generierung." — der Button war
        nicht mehr tot, aber er funktionierte auch nie. Die Mock-Tests oben können das
        strukturell nicht sehen, deshalb dieser Bind gegen die echte Signatur.
        """
        fake_task, _ = self._press()
        from tasks.p09_chat_ideas_task import deliver_ideas_to_chat

        # `conftest.py` stubbt celery, wenn es fehlt — dann ist der Task die nackte
        # Funktion und `self` steht noch in der Signatur. Genau deshalb greift die
        # echte celery-Prüfung hier nie und der Defekt überlebte. Also `self`
        # abziehen und binden wie `.delay()` es täte.
        sig = inspect.signature(deliver_ideas_to_chat)
        params = list(sig.parameters.values())
        if params and params[0].name == "self":
            sig = sig.replace(parameters=params[1:])
        sig.bind(**fake_task.delay.call_args.kwargs)
