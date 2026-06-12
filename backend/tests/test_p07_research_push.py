"""Tests für P07 Telegram-Push (Issue #35).

TDD: _build_push_message, _push_findings_to_telegram und
run_research_for_tenant mit gemocktem asyncio.run + Push-Seam.

Anti-Pollution-Strategie
------------------------
* Baut auf _telegram_task_env auf (liefert sqlalchemy/config/models.base/
  celery/api.telegram/tasks.telegram_task konsistent ein).
* p07_research_task wird via spec_from_file_location EINMAL geladen — Guard
  gegen wiederholte Ausführung (``hasattr(_build_push_message)`` check).
* services.llm, services.nextcloud und config werden mit if-not-in-sys.modules
  Guards gesetzt — niemals wholesale überschrieben.
* asyncio.run und _run_for_tenant_async werden per patch.object gemockt —
  kein echter DB/LLM-Call in irgendeinem Test.

Pflichtcheck (beide Reihenfolgen grün):
  PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_p07_research_push.py \
      tests/test_session_post_task.py tests/test_telegram_inbound_routing.py \
      tests/test_p08_service.py tests/test_layer1_extraction.py \
      tests/test_wizard_phases.py -q
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import types
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Geteilte Stub-Umgebung ZUERST — liefert sqlalchemy/config/models.base/
# celery/api.telegram/tasks.telegram_task/services.* konsistent ein.
# ---------------------------------------------------------------------------
from tests import _telegram_task_env as _env  # noqa: F401

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _stub(name: str) -> types.ModuleType:
    """Get-or-create Stub — nie existierende Module überschreiben."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# services.llm.set_llm_tenant — p07_research_task importiert es lazy in
# _process_item_async. Sicherstellen dass set_llm_tenant vorhanden ist.
# ---------------------------------------------------------------------------
import services as _services_pkg

_llm_mod = sys.modules.get("services.llm") or _stub("services.llm")
if not hasattr(_llm_mod, "set_llm_tenant"):
    _llm_mod.set_llm_tenant = MagicMock()
if not hasattr(_llm_mod, "llm_service"):
    _llm_mod.llm_service = MagicMock()
_services_pkg.llm = _llm_mod

# ---------------------------------------------------------------------------
# p07_research_task — EINMAL laden; bei Wiederholungsimport wiederverwenden.
# Guard: _build_push_message fehlt in einem MagicMock-Stub → real laden.
# ---------------------------------------------------------------------------
_existing_p07 = sys.modules.get("tasks.p07_research_task")
if _existing_p07 is None or not hasattr(_existing_p07, "_build_push_message"):
    _spec = _ilu.spec_from_file_location(
        "tasks.p07_research_task",
        os.path.join(_BACKEND_DIR, "tasks", "p07_research_task.py"),
    )
    _p07_mod = _ilu.module_from_spec(_spec)
    sys.modules["tasks.p07_research_task"] = _p07_mod
    _spec.loader.exec_module(_p07_mod)
    sys.modules["tasks"].p07_research_task = _p07_mod

p07 = sys.modules["tasks.p07_research_task"]

# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------

_FINDING_A = {
    "id": "finding-1",
    "title": "KI verändert Recruiting",
    "hooks": [
        "So nutze ich KI für schnelleres Hiring.",
        "Was 100 Bewerber filtert in 5 Minuten.",
        "Der Recruiting-Trend den keiner kennt.",
    ],
}
_FINDING_B = {
    "id": "finding-2",
    "title": "Remote Work Kosten steigen",
    "hooks": [
        "Remote-Arbeit wird teurer — das ist der Grund.",
        "Mein Setup-Experiment nach 6 Monaten.",
    ],
}
_FINDING_C = {
    "id": "finding-3",
    "title": "Green Tech Investitionen",
    "hooks": ["Warum ich jetzt in Green Tech setze."],
}
_FINDING_D = {
    "id": "finding-4",
    "title": "Viertes Finding",
    "hooks": ["Hook D1", "Hook D2"],
}


# ---------------------------------------------------------------------------
# _build_push_message
# ---------------------------------------------------------------------------


class TestBuildPushMessage:
    def test_single_finding_contains_title_and_hooks(self):
        msg = p07._build_push_message([_FINDING_A])
        assert "KI verändert Recruiting" in msg
        assert "So nutze ich KI" in msg
        assert "Was 100 Bewerber" in msg

    def test_top_n_capped(self):
        """Standardmäßig Top-3, Finding-4 soll nicht im Haupttext erscheinen."""
        findings = [_FINDING_A, _FINDING_B, _FINDING_C, _FINDING_D]
        msg = p07._build_push_message(findings, top_n=3)
        assert "KI verändert Recruiting" in msg
        assert "Remote Work" in msg
        assert "Green Tech" in msg
        # Viertes finding nicht im Haupttitel, aber im Überlauf-Hinweis
        assert "Viertes Finding" not in msg
        assert "+ 1 weitere" in msg

    def test_no_overflow_hint_when_within_top_n(self):
        msg = p07._build_push_message([_FINDING_A, _FINDING_B], top_n=3)
        assert "weitere Findings" not in msg

    def test_empty_findings_returns_something(self):
        """Leere Liste → leerer String (Aufrufer prüft vor dem Senden)."""
        msg = p07._build_push_message([])
        # Nur die Überschrift, kein Crash
        assert isinstance(msg, str)

    def test_finding_with_no_hooks_skips_bullets(self):
        no_hooks = {"id": "x", "title": "Ohne Hooks", "hooks": []}
        msg = p07._build_push_message([no_hooks])
        assert "Ohne Hooks" in msg
        # Kein Bullet-Symbol da keine hooks
        assert "•" not in msg

    def test_title_truncated_at_120_chars(self):
        long_title = "A" * 200
        f = {"id": "x", "title": long_title, "hooks": ["Hook1"]}
        msg = p07._build_push_message([f])
        # 120 A's erscheinen, kein 200-Zeichen-Block
        assert "A" * 120 in msg
        assert "A" * 121 not in msg

    def test_hook_truncated_at_200_chars(self):
        long_hook = "B" * 250
        f = {"id": "x", "title": "Titel", "hooks": [long_hook]}
        msg = p07._build_push_message([f])
        assert "B" * 200 in msg
        assert "B" * 201 not in msg

    def test_top_n_custom(self):
        findings = [_FINDING_A, _FINDING_B, _FINDING_C]
        msg = p07._build_push_message(findings, top_n=2)
        assert "KI verändert Recruiting" in msg
        assert "Remote Work" in msg
        assert "Green Tech" not in msg
        assert "+ 1 weitere" in msg


# ---------------------------------------------------------------------------
# _push_findings_to_telegram
# ---------------------------------------------------------------------------


class TestPushFindingsToTelegram:
    def test_active_chat_id_sends_message(self):
        """Aktiver chat_id → _send_telegram_message wird aufgerufen."""
        resolve_mock = MagicMock(return_value=1234)
        send_mock = MagicMock()
        with (
            patch("tasks.telegram_task._resolve_chat_id", resolve_mock, create=True),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
        ):
            result = p07._push_findings_to_telegram("tenant-A", [_FINDING_A, _FINDING_B])
        assert result is True
        send_mock.assert_called_once()
        call_args = send_mock.call_args[0]
        assert call_args[0] == 1234
        # Nachricht enthält Findings-Titel
        assert "KI verändert Recruiting" in call_args[1]

    def test_no_chat_id_skip_no_crash(self):
        """Kein aktiver chat_id → kein Send, kein Crash, gibt False zurück."""
        resolve_mock = MagicMock(return_value=None)
        send_mock = MagicMock()
        with (
            patch("tasks.telegram_task._resolve_chat_id", resolve_mock, create=True),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
        ):
            result = p07._push_findings_to_telegram("tenant-B", [_FINDING_A])
        assert result is False
        send_mock.assert_not_called()

    def test_empty_findings_returns_false_no_send(self):
        """Leere findings-Liste → sofort False, kein resolve_chat_id-Call."""
        resolve_mock = MagicMock(return_value=9999)
        send_mock = MagicMock()
        with (
            patch("tasks.telegram_task._resolve_chat_id", resolve_mock, create=True),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
        ):
            result = p07._push_findings_to_telegram("tenant-C", [])
        assert result is False
        send_mock.assert_not_called()
        resolve_mock.assert_not_called()

    def test_send_error_fail_open(self):
        """_send_telegram_message wirft → gibt False zurück, kein Raise."""
        resolve_mock = MagicMock(return_value=5555)
        send_mock = MagicMock(side_effect=RuntimeError("telegram down"))
        with (
            patch("tasks.telegram_task._resolve_chat_id", resolve_mock, create=True),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
        ):
            result = p07._push_findings_to_telegram("tenant-D", [_FINDING_A])
        assert result is False

    def test_resolve_error_fail_open(self):
        """_resolve_chat_id wirft → gibt False zurück, kein Raise."""
        resolve_mock = MagicMock(side_effect=ConnectionError("db down"))
        send_mock = MagicMock()
        with (
            patch("tasks.telegram_task._resolve_chat_id", resolve_mock, create=True),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
        ):
            result = p07._push_findings_to_telegram("tenant-E", [_FINDING_A])
        assert result is False
        send_mock.assert_not_called()

    def test_message_capped_at_telegram_max(self):
        """Nachricht wird bei _TELEGRAM_MAX_CHARS abgeschnitten."""
        # 10 Findings mit sehr langen Hooks → Nachricht wäre > 4000 Zeichen
        many = [{"id": f"f{i}", "title": f"Titel {i}", "hooks": ["X" * 200]} for i in range(10)]
        captured = []

        def capturing_send(chat_id, msg):
            captured.append(msg)

        resolve_mock = MagicMock(return_value=777)
        with (
            patch("tasks.telegram_task._resolve_chat_id", resolve_mock, create=True),
            patch("api.telegram._send_telegram_message", capturing_send, create=True),
        ):
            p07._push_findings_to_telegram("tenant-F", many)

        assert len(captured) == 1
        assert len(captured[0]) <= p07._TELEGRAM_MAX_CHARS

    def test_tenant_scope_only_own_chat_id(self):
        """E3: Jeder Tenant bekommt nur seine eigene chat_id (Isolation durch _resolve_chat_id)."""
        calls: list[tuple] = []

        def scoped_resolve(tenant_id):
            return {"tenant-X": 1111, "tenant-Y": 2222}.get(tenant_id)

        def capturing_send(chat_id, msg):
            calls.append((chat_id, msg))

        with (
            patch("tasks.telegram_task._resolve_chat_id", scoped_resolve, create=True),
            patch("api.telegram._send_telegram_message", capturing_send, create=True),
        ):
            p07._push_findings_to_telegram("tenant-X", [_FINDING_A])
            p07._push_findings_to_telegram("tenant-Y", [_FINDING_B])

        assert len(calls) == 2
        # Tenant-X chat_id 1111, Tenant-Y chat_id 2222 — keine Kreuz-Zustellung
        assert calls[0][0] == 1111
        assert calls[1][0] == 2222
        # Inhalte sind tenant-spezifisch (different findings)
        assert "KI verändert Recruiting" in calls[0][1]
        assert "Remote Work" in calls[1][1]
        assert "KI verändert Recruiting" not in calls[1][1]


# ---------------------------------------------------------------------------
# run_research_for_tenant — Integration mit gemocktem asyncio.run
# ---------------------------------------------------------------------------


class TestRunResearchForTenant:
    """Testet den Celery-Task über seinen sync-Einstiegspunkt.

    asyncio.run und _push_findings_to_telegram werden gemockt — kein
    echter DB/LLM/Telegram-Call.
    """

    def _run_task(
        self,
        async_result: dict,
        push_return: bool = True,
    ):
        """Fährt run_research_for_tenant mit gemocktem asyncio.run + Push."""
        push_mock = MagicMock(return_value=push_return)
        # bind=True → self ist erster Arg; wir rufen die Funktion direkt
        # (bypass Celery), self=None ist ausreichend für den Logik-Pfad.
        with (
            patch.object(p07, "asyncio") as mock_asyncio,
            patch.object(p07, "_push_findings_to_telegram", push_mock),
        ):
            mock_asyncio.run.return_value = async_result
            result = p07.run_research_for_tenant(None, "tenant-T")
        return result, push_mock

    def test_push_called_when_new_findings(self):
        """Neue Findings → _push_findings_to_telegram wird aufgerufen."""
        async_result = {
            "tenant_id": "tenant-T",
            "inserted": 2,
            "skipped": 0,
            "new_findings": [_FINDING_A, _FINDING_B],
        }
        result, push_mock = self._run_task(async_result, push_return=True)
        push_mock.assert_called_once_with("tenant-T", [_FINDING_A, _FINDING_B])
        assert result["push_sent"] is True

    def test_no_push_when_no_new_findings(self):
        """Keine neuen Findings → Push wird übersprungen."""
        async_result = {
            "tenant_id": "tenant-T",
            "inserted": 0,
            "skipped": 5,
            "new_findings": [],
        }
        result, push_mock = self._run_task(async_result, push_return=False)
        push_mock.assert_not_called()
        assert result["push_sent"] is False

    def test_new_findings_not_in_task_return(self):
        """new_findings wird aus dem Task-Return entfernt (internes Feld)."""
        async_result = {
            "tenant_id": "tenant-T",
            "inserted": 1,
            "skipped": 0,
            "new_findings": [_FINDING_A],
        }
        result, _ = self._run_task(async_result)
        assert "new_findings" not in result

    def test_push_fail_does_not_break_task_result(self):
        """Push schlägt fehl → Task-Ergebnis bleibt intakt (fail-open)."""
        async_result = {
            "tenant_id": "tenant-T",
            "inserted": 1,
            "skipped": 0,
            "new_findings": [_FINDING_A],
        }
        result, push_mock = self._run_task(async_result, push_return=False)
        # Kernfelder des Tasks bleiben korrekt
        assert result["inserted"] == 1
        assert result["skipped"] == 0
        assert result["tenant_id"] == "tenant-T"
        # push_sent zeigt Fehlschlag an, bricht aber nicht
        assert result["push_sent"] is False

    def test_asyncio_run_exception_returns_error_dict(self):
        """asyncio.run wirft → Task gibt Fehler-Dict zurück (bisheriges Verhalten)."""
        push_mock = MagicMock()
        with (
            patch.object(p07, "asyncio") as mock_asyncio,
            patch.object(p07, "_push_findings_to_telegram", push_mock),
        ):
            mock_asyncio.run.side_effect = RuntimeError("DB connection failed")
            result = p07.run_research_for_tenant(None, "tenant-T")
        assert result["status"] == "error"
        assert "DB connection" in result["reason"]
        push_mock.assert_not_called()

    def test_idempotency_second_run_no_push(self):
        """Zweiter Lauf mit leerem new_findings (alles bereits existiert) → kein Push."""
        # Erster Lauf: 2 neue Findings
        first_run = {
            "tenant_id": "tenant-T",
            "inserted": 2,
            "skipped": 0,
            "new_findings": [_FINDING_A, _FINDING_B],
        }
        # Zweiter Lauf: alles bereits in DB, _process_item_async gibt None zurück
        second_run = {
            "tenant_id": "tenant-T",
            "inserted": 0,
            "skipped": 2,
            "new_findings": [],
        }
        push_mock = MagicMock(return_value=True)
        with (
            patch.object(p07, "asyncio") as mock_asyncio,
            patch.object(p07, "_push_findings_to_telegram", push_mock),
        ):
            mock_asyncio.run.return_value = first_run
            p07.run_research_for_tenant(None, "tenant-T")

            mock_asyncio.run.return_value = second_run
            p07.run_research_for_tenant(None, "tenant-T")

        # Push nur beim ersten Lauf (1 Call)
        assert push_mock.call_count == 1
