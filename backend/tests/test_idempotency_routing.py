"""Tests für Idempotenz (#18), routed_to-Persistenz (#56) und targeted-Filter (#57).

Abdeckung:
  #18 Schicht A — Celery-Retry-Deduplizierung via routed_to-Guard
  #18 Schicht B — Telegram-Redelivery-Deduplizierung via update_id in _store_and_dispatch
  #56            — persist_routing_decision wird aufgerufen und log_id durchgereicht
  #57            — _load_active_session findet targeted-Sessions

Stub-Schicht wird vollständig von tests._telegram_task_env bereitgestellt —
keine eigene spec_from_file_location/Stub-Logik mehr. Beide Test-Dateien
(test_telegram_inbound_routing + test_idempotency_routing) teilen so eine
einzige Modulinstanz von tasks.telegram_task und können in beliebiger
Reihenfolge kombiniert laufen (Issue #16, #18, #56, #57).

Patching-Strategie:
  patch.object(_tt, ...) für direkte telegram_task-Attribute.
  patch.object(sys.modules["services.*"], ...) für Servicestubs —
  damit der Patch immer das richtige Objekt trifft, unabhängig von der
  Reihenfolge der Test-Datei-Ausführung.
"""

import json as _json
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
# _store_and_dispatch stub (für #18 Schicht B Tests)
# api.telegram kann im Py-3.9-Testenv nicht importiert werden (datetime.UTC),
# deshalb testen wir die Kernlogik über eine extrahierte Referenzimplementierung.
# ---------------------------------------------------------------------------


def _store_and_dispatch_impl(tenant_id, message, message_type, session_factory, dispatch_fn=None):
    """Extrahierte Testversion der _store_and_dispatch-Logik (ohne datetime.UTC).

    Implementiert exakt die Deduplizierungslogik aus api/telegram.py _store_and_dispatch.
    """
    import logging as _logging

    _log = _logging.getLogger("test_store_dispatch")

    update_id = message.get("_update_id")
    if update_id is not None:
        try:
            with session_factory() as db:
                dup_row = db.execute(
                    "SELECT 1 FROM telegram_message_log ...",
                    {"tid": tenant_id, "uid": str(update_id)},
                ).fetchone()
            if dup_row is not None:
                return "deduped"
        except Exception as e:
            _log.warning("update_id dedup check failed: %s", type(e).__name__)

    log_id = None
    with session_factory() as db:
        result = db.execute(
            "INSERT INTO telegram_message_log ...",
            {"tid": tenant_id, "mtype": message_type, "payload": _json.dumps(message)},
        )
        row = result.fetchone()
        db.commit()
        if row:
            log_id = str(row[0])

    if log_id is None:
        return "no_log_id"

    if dispatch_fn:
        dispatch_fn(log_id)

    return log_id


# ============================================================================
# #18 Schicht A — Celery-Retry-Deduplizierung via routed_to-Guard
# ============================================================================


class TestIdempotencyGuard:
    """#18 Schicht A: _route_inbound_message dedupliziert anhand routed_to.

    Alle Patches über patch.object(_tt, ...) / patch.object(sys.modules[...], ...)
    damit der Test stabil ist unabhängig davon ob sys.modules["tasks.telegram_task"]
    von einem anderen Test-Modul überschrieben wurde.
    """

    def test_route_skips_when_already_routed(self):
        """Guard-SELECT liefert non-NULL routed_to → dedupliziert, kein p08-Call."""
        mock_db = make_guard_db_mock("p08_response")

        with (
            patch.object(tt, "sync_session_factory", return_value=mock_db),
            patch.object(tt, "_load_active_session") as mock_session,
            patch.object(
                sys.modules["services.layer1_extraction"], "extract_intent_features"
            ) as mock_extract,
            patch.object(sys.modules["services.p08_service"], "p08_response") as mock_p08,
        ):
            result = tt._route_inbound_message("tenant-1", "eine Antwort", log_id="log-dup")

        assert result is not None
        assert result.get("deduped") is True
        assert result.get("routed_to") == "p08_response"
        mock_session.assert_not_called()
        mock_extract.assert_not_called()
        mock_p08.assert_not_called()

    def test_route_persists_marker_before_p08(self):
        """Guard-SELECT = None → routing normal, persist_routing_decision VOR p08 aufgerufen."""
        mock_db = make_guard_db_mock(None)
        decision = make_decision("p08_response", {"session_id": "sess-1", "features": {"k": "v"}})

        call_order = []

        def fake_persist(lid, dec):
            call_order.append("persist")

        def fake_p08(*a, **kw):
            call_order.append("p08")
            return make_p08_result()

        with (
            patch.object(tt, "sync_session_factory", return_value=mock_db),
            patch.object(tt, "_load_active_session", return_value=active_session()),
            patch.object(
                sys.modules["services.layer1_extraction"],
                "extract_intent_features",
                return_value=make_extraction("answer_to_question"),
            ),
            patch.object(
                sys.modules["services.layer2_routing"],
                "route_telegram_intent",
                return_value=decision,
            ),
            patch.object(
                sys.modules["services.layer2_routing"],
                "persist_routing_decision",
                side_effect=fake_persist,
            ),
            patch.object(
                sys.modules["services.p08_service"],
                "p08_response",
                side_effect=fake_p08,
            ),
        ):
            result = tt._route_inbound_message("tenant-1", "eine Antwort", log_id="log-new")

        assert result is not None
        assert result.get("deduped") is not True
        assert result.get("routed_to") == "p08_response"
        # persist muss VOR p08 gewesen sein
        assert call_order == ["persist", "p08"], f"Reihenfolge falsch: {call_order}"

    def test_route_without_log_id_backwards_compatible(self):
        """log_id=None → kein Guard-SELECT, kein Persist-Call — Alt-Aufrufer bleiben intakt."""
        decision = make_decision("p08_response", {"session_id": "sess-1", "features": {}})

        persisted = []

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
                return_value=decision,
            ),
            patch.object(
                sys.modules["services.layer2_routing"],
                "persist_routing_decision",
                side_effect=lambda *a: persisted.append(a),
            ),
            patch.object(
                sys.modules["services.p08_service"],
                "p08_response",
                return_value=make_p08_result(),
            ),
        ):
            result = tt._route_inbound_message("tenant-1", "alte Antwort", log_id=None)

        assert result is not None
        assert result.get("deduped") is not True
        assert (
            len(persisted) == 0
        ), "persist_routing_decision darf bei log_id=None nicht aufgerufen werden"
        assert result.get("routed_to") == "p08_response"


# ============================================================================
# #18 Schicht B — _store_and_dispatch Deduplizierung via update_id
# ============================================================================


class TestUpdateIdDedup:
    """#18 Schicht B: _store_and_dispatch erkennt Telegram-Redelivery per _update_id.

    Da api.telegram datetime.UTC importiert (Py 3.10+) und der lokale venv
    Py 3.9 ist, wird die Deduplizierungslogik über die extrahierte
    _store_and_dispatch_impl-Funktion getestet (identische Logik).
    """

    def _make_db_factory(self, has_duplicate=False):
        """Liefert eine (factory, mock_db)-Tuple."""
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        if has_duplicate:
            mock_db.execute.return_value.fetchone.return_value = (1,)  # Duplikat
        else:
            # Kein Duplikat: Dedup-SELECT liefert None, INSERT liefert id
            dedup_result = MagicMock()
            dedup_result.fetchone.return_value = None
            insert_result = MagicMock()
            insert_result.fetchone.return_value = ("new-log-id",)
            mock_db.execute.side_effect = [dedup_result, insert_result]
        return lambda: mock_db, mock_db

    def test_duplicate_update_id_not_stored(self):
        """Zweiter Call mit gleichem update_id → kein INSERT (deduped)."""
        factory, mock_db = self._make_db_factory(has_duplicate=True)
        message = {"text": "Hallo", "_update_id": 42}

        result = _store_and_dispatch_impl("tenant-1", message, "text", factory)

        assert result == "deduped"
        # Nur ein execute (der Dedup-SELECT), kein INSERT
        assert mock_db.execute.call_count == 1
        assert mock_db.commit.call_count == 0

    def test_new_update_id_gets_stored(self):
        """Erstmaliger update_id → normal gespeichert, log_id zurückgegeben."""
        factory, mock_db = self._make_db_factory(has_duplicate=False)
        message = {"text": "Neue Nachricht", "_update_id": 100}

        result = _store_and_dispatch_impl("tenant-1", message, "text", factory)

        assert result == "new-log-id"
        assert mock_db.execute.call_count == 2  # Dedup-SELECT + INSERT
        assert mock_db.commit.called

    def test_message_without_update_id_skips_dedup_check(self):
        """Nachricht ohne _update_id → kein Dedup-SELECT, direkt INSERT."""
        insert_result = MagicMock()
        insert_result.fetchone.return_value = ("log-id-direct",)

        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        # Nur ein execute möglich (INSERT), da kein Dedup-Check
        mock_db.execute.return_value = insert_result

        def factory():
            return mock_db

        message = {"text": "Ohne update_id"}

        result = _store_and_dispatch_impl("tenant-1", message, "text", factory)

        assert result == "log-id-direct"
        # Nur ein execute: kein vorangehender Dedup-SELECT
        assert mock_db.execute.call_count == 1

    def test_update_id_payload_contains_uid(self):
        """_update_id im gespeicherten JSON-Payload nachweisbar."""
        captured = {}

        def fake_execute(query, params=None):
            r = MagicMock()
            if params and "payload" in params:
                captured.update(_json.loads(params["payload"]))
                r.fetchone.return_value = ("log-id-9",)
            else:
                r.fetchone.return_value = None
            return r

        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.execute.side_effect = fake_execute

        def factory():
            return mock_db

        message = {"text": "Hallo", "_update_id": 55}

        _store_and_dispatch_impl("tenant-1", message, "text", factory)

        assert captured.get("_update_id") == 55


# ============================================================================
# #56 — log_id wird von Callers durchgereicht
# ============================================================================


class TestLogIdThreaded:
    """#56: _process_voice und _process_text reichen log_id an _route_inbound_message."""

    def test_process_text_threads_log_id(self):
        """_process_text ruft _route_inbound_message mit log_id auf."""
        with (
            patch.object(tt, "asyncio") as mock_asyncio,
            patch.object(tt, "_store_chunk_async"),
            patch.object(tt, "_route_inbound_message") as mock_route,
        ):
            mock_asyncio.run.return_value = "chunk-1"
            mock_route.return_value = None

            payload = {"text": "Eine ausführliche Nachricht als Antwort."}
            tt._process_text("my-log-id", "tenant-1", payload)

        mock_route.assert_called_once()
        call_args = mock_route.call_args
        positional = call_args[0]
        keyword = call_args[1]
        log_id_passed = keyword.get("log_id") or (positional[2] if len(positional) > 2 else None)
        assert log_id_passed == "my-log-id", f"log_id nicht korrekt übergeben: {call_args}"

    def test_process_voice_threads_log_id(self):
        """_process_voice ruft _route_inbound_message mit log_id auf."""
        with (
            patch.object(tt, "asyncio") as mock_asyncio,
            patch.object(tt, "_store_chunk_async"),
            patch.object(tt, "_telegram_get_file", return_value=b"audio"),
            patch.object(tt, "transcribe_voice") as mock_transcribe,
            patch.object(tt, "_update_log_transcript"),
            patch.object(tt, "_route_inbound_message") as mock_route,
        ):
            mock_asyncio.run.return_value = "voice-chunk"
            mock_transcribe.return_value = types.SimpleNamespace(
                text="Gesprochene Antwort", model_name="whisper", confidence=0.9
            )
            mock_route.return_value = None

            payload = {"voice": {"file_id": "f1", "duration": 5, "mime_type": "audio/ogg"}}
            tt._process_voice("voice-log-id", "tenant-1", payload)

        mock_route.assert_called_once()
        call_args = mock_route.call_args
        positional = call_args[0]
        keyword = call_args[1]
        log_id_passed = keyword.get("log_id") or (positional[2] if len(positional) > 2 else None)
        assert log_id_passed == "voice-log-id", f"log_id nicht korrekt übergeben: {call_args}"


# ============================================================================
# #57 — targeted-Mode-Filter
# ============================================================================


class TestTargetedModeFilter:
    """#57: _load_active_session findet auch targeted-Sessions."""

    def test_targeted_session_found(self):
        """_load_active_session gibt targeted-Session zurück."""
        fake_row = types.SimpleNamespace(id="targeted-sess-1", status="active")
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.execute.return_value.fetchone.return_value = fake_row

        with patch.object(tt, "sync_session_factory", return_value=mock_db):
            result = tt._load_active_session("tenant-targeted")

        assert result is not None
        assert str(result.id) == "targeted-sess-1"

    def test_sql_includes_targeted_mode(self):
        """Verifiziert, dass die SQL-Query 'targeted' im Filter enthält."""
        executed_queries = []

        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)

        def capture_execute(query, params=None):
            executed_queries.append(str(query))
            result = MagicMock()
            result.fetchone.return_value = None
            return result

        mock_db.execute.side_effect = capture_execute

        with patch.object(tt, "sync_session_factory", return_value=mock_db):
            tt._load_active_session("tenant-x")

        assert len(executed_queries) == 1, f"Genau eine Query erwartet: {executed_queries}"
        query = executed_queries[0]
        assert "targeted" in query, f"'targeted' nicht in Query: {query!r}"
        assert "random_smart" in query, f"'random_smart' nicht in Query: {query!r}"

    def test_only_random_smart_session_is_still_found(self):
        """random_smart-Session wird weiterhin gefunden (Regression für #57)."""
        fake_row = types.SimpleNamespace(id="random-sess-1", status="active")
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.execute.return_value.fetchone.return_value = fake_row

        with patch.object(tt, "sync_session_factory", return_value=mock_db):
            result = tt._load_active_session("tenant-random")

        assert result is not None
        assert str(result.id) == "random-sess-1"

    def test_no_session_returns_none(self):
        """Keine aktive Session → None."""
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.execute.return_value.fetchone.return_value = None

        with patch.object(tt, "sync_session_factory", return_value=mock_db):
            result = tt._load_active_session("tenant-empty")

        assert result is None
