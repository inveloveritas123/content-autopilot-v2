"""Tests für tasks.session_timeout_task — liegengebliebene Gespräche beenden.

Bot-Sessions hatten kein TTL. Eine unbeantwortete Session blieb für immer
`active` und verschluckte jede spätere Nachricht des Tenants als „Antwort" auf
eine Frage von vorgestern (belegt: Erics `82c87b77…`, seit 12:33 UTC hängend).

Der wichtigste Wächter hier ist `COALESCE`: `p08_opener` schreibt
`last_message_at` NICHT, die Spalte bleibt NULL bis zur ersten Antwort. Ein TTL
auf `last_message_at` allein liesse ausgerechnet die nie beantworteten Sessions
nie ablaufen — also genau den Fall, für den der Task da ist.

Baut auf der GETEILTEN Stub-Umgebung _telegram_task_env auf.
"""

from __future__ import annotations

import importlib.util as _ilu
import json
import os
import sys
from unittest.mock import MagicMock, patch

from tests import _telegram_task_env as _env  # noqa: F401

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_spec = _ilu.spec_from_file_location(
    "tasks.session_timeout_task",
    os.path.join(_BACKEND_DIR, "tasks", "session_timeout_task.py"),
)
_stt = _ilu.module_from_spec(_spec)
sys.modules["tasks.session_timeout_task"] = _stt
_spec.loader.exec_module(_stt)
sys.modules["tasks"].session_timeout_task = _stt


def _ctx(fetchall_val=None, rowcount=1):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.execute.return_value.fetchall.return_value = fetchall_val or []
    ctx.execute.return_value.rowcount = rowcount
    return ctx


def _row(session_id, tenant_id, messages):
    werte = (session_id, tenant_id, messages)
    row = MagicMock()
    row.__getitem__ = lambda self, i: werte[i]
    return row


_OPENER_ONLY = [{"bot": "Erzähl mal!", "user_features_summary": None, "user_transcript": None}]
_MIT_ANTWORT = [
    {"bot": "Erzähl mal!", "user_features_summary": None, "user_transcript": None},
    {
        "bot": "Und dann?",
        "user_features_summary": '{"k":"v"}',
        "user_transcript": "Wir sparen eine Stunde.",
    },
]


class TestCoalesce:
    """Der Fall, der ohne COALESCE unsichtbar bliebe."""

    def test_abfrage_nutzt_coalesce_auf_created_at(self):
        """Statischer Wächter: p08_opener schreibt last_message_at nicht.

        Ein TTL auf `last_message_at` allein liesse die nie beantworteten
        Sessions NIE ablaufen — belegt an Erics `6ec54be4…` und `82c87b77…`
        (beide last_message_at NULL). Der Test liest die tatsächliche SQL.
        """
        sql_gesehen = []

        def fake_factory():
            ctx = _ctx()

            def execute(stmt, params=None):
                sql_gesehen.append(str(stmt))
                res = MagicMock()
                res.fetchall.return_value = []
                res.rowcount = 0
                return res

            ctx.execute = execute
            return ctx

        with patch.object(_stt, "sync_session_factory", fake_factory):
            _stt.expire_stale_sessions()

        assert sql_gesehen, "Es wurde gar keine Abfrage abgesetzt"
        sql = " ".join(sql_gesehen).lower()
        assert "coalesce(last_message_at, created_at)" in sql.replace("\n", " ")

    def test_timeout_ist_24_stunden(self):
        assert _stt.SESSION_TIMEOUT_HOURS == 24


class TestVerhalten:
    def _lauf(self, rows, rowcount=1):
        """Fährt den Task mit einer festen Ergebnismenge und protokolliert Updates."""
        updates = []

        class _Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def execute(self_inner, stmt, params=None):
                res = MagicMock()
                if "SELECT" in str(stmt).upper():
                    res.fetchall.return_value = rows
                else:
                    updates.append(params or {})
                res.rowcount = rowcount
                return res

            def commit(self_inner):
                return None

        with (
            patch.object(_stt, "sync_session_factory", _Ctx),
            patch.object(_stt, "_sende_ansage", return_value=True) as ansage,
        ):
            ergebnis = _stt.expire_stale_sessions()
        return ergebnis, updates, ansage

    def test_mit_antwort_wird_closed_damit_der_post_entsteht(self):
        """`session_post_task` überspringt alles mit `status != 'closed'`.

        Mit 'expired' entstünde kein Post — obwohl die Spec „Post bauen und
        senden" verlangt. 'closed' = es gibt etwas zu schreiben.
        """
        rows = [_row("s1", "t1", json.dumps(_MIT_ANTWORT))]
        ergebnis, updates, ansage = self._lauf(rows)

        assert [u.get("st") for u in updates] == ["closed"]
        assert ergebnis["expired"] == 1
        ansage.assert_called_once()

    def test_ohne_antwort_wird_expired_und_kein_post(self):
        """Testfall 14, zweite Hälfte: nur die Ansage, kein Post."""
        rows = [_row("s2", "t1", json.dumps(_OPENER_ONLY))]
        ergebnis, updates, ansage = self._lauf(rows)

        assert [u.get("st") for u in updates] == ["expired"]
        assert ergebnis["posts_enqueued"] == 0
        ansage.assert_called_once()

    def test_frisches_gespraech_bleibt_unberuehrt(self):
        """Testfall 15: Was die Abfrage nicht liefert, wird nicht angefasst."""
        ergebnis, updates, ansage = self._lauf([])

        assert updates == []
        assert ergebnis == {"status": "ok", "expired": 0, "posts_enqueued": 0}
        ansage.assert_not_called()

    def test_zwischenzeitlich_beantwortet_wird_nicht_beendet(self):
        """rowcount=0 heisst: die Session war beim UPDATE nicht mehr 'active'.

        Ohne diese Prüfung würde der Task eine gerade beantwortete Session
        beenden — das Rennen zwischen Beat und Worker.
        """
        rows = [_row("s3", "t1", json.dumps(_MIT_ANTWORT))]
        ergebnis, _updates, ansage = self._lauf(rows, rowcount=0)

        assert ergebnis["expired"] == 0
        ansage.assert_not_called()

    def test_abfragefehler_beendet_nichts(self):
        """Fail-safe: ein DB-Fehler darf keine Session anfassen."""

        class _Boom:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def execute(self_inner, *a, **kw):
                raise RuntimeError("db weg")

        with patch.object(_stt, "sync_session_factory", _Boom):
            ergebnis = _stt.expire_stale_sessions()

        assert ergebnis["status"] == "error"


class TestAntwortErkennung:
    def test_nur_opener_zaehlt_nicht_als_antwort(self):
        assert _stt._hat_antworten(json.dumps(_OPENER_ONLY)) is False

    def test_rohtext_zaehlt(self):
        assert _stt._hat_antworten(json.dumps(_MIT_ANTWORT)) is True

    def test_liste_statt_json_string(self):
        """jsonb kommt je nach Treiber als Liste oder als String an."""
        assert _stt._hat_antworten(_MIT_ANTWORT) is True

    def test_kaputte_daten_fail_safe(self):
        assert _stt._hat_antworten("{kein json") is False
        assert _stt._hat_antworten(None) is False

    def test_leerer_rohtext_zaehlt_nicht(self):
        nachrichten = [{"bot": "Frage?", "user_transcript": "   ", "user_features_summary": None}]
        assert _stt._hat_antworten(json.dumps(nachrichten)) is False


class TestRegistrierung:
    def test_task_haengt_im_beat_plan_und_in_include(self):
        """Ein Task, der nicht im Beat-Plan steht, läuft nie.

        Der Wächter liest die Quelle von celery_app.py: der Celery-Stub der
        Tests hält `beat_schedule`/`include` nicht.
        """
        with open(os.path.join(_BACKEND_DIR, "tasks", "celery_app.py"), encoding="utf-8") as f:
            quelle = f.read()
        assert "tasks.session_timeout_task.expire_stale_sessions" in quelle
        assert '"tasks.session_timeout_task",' in quelle
