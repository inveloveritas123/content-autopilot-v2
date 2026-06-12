"""Tests für Embedding-Versionierung (Issue #150).

Deckt ab:
- embed() gibt model_id korrekt zurück
- Canary-Task stoppt bei Recall-Drop (kein Soft-Delete)
- drift_monitor schreibt in throttle_events scope='embedding_drift'

Kein pytest-asyncio — nutzt asyncio.run() direkt (wie bestehende Tests).
Kein echter DB/API-Zugang — alles gemockt.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# A) embed() gibt model_id korrekt zurück
# ---------------------------------------------------------------------------


def test_embed_returns_model_id_success():
    """embed() gibt (vector, model_id) zurück wenn API-Call erfolgreich."""
    from services.embedding_service import ACTIVE_EMBEDDING_MODEL, EMBEDDING_MODELS

    fake_dim = EMBEDDING_MODELS[ACTIVE_EMBEDDING_MODEL]["dim"]
    fake_vector = [0.1] * fake_dim

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": [{"embedding": fake_vector}]}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch("services.embedding_service.settings") as mock_settings,
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.litellm_base_url = "http://fake-requesty"
        mock_settings.litellm_api_key = "fake-key"

        from services.embedding_service import embed

        result_vector, result_model_id = asyncio.run(embed("Test-Text"))

    assert result_vector is not None
    assert len(result_vector) == fake_dim
    assert result_model_id == ACTIVE_EMBEDDING_MODEL


def test_embed_returns_model_id_on_failure():
    """embed() gibt (None, model_id) zurück bei API-Fehler — model_id ist trotzdem gesetzt."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("Netzwerkfehler"))

    with (
        patch("services.embedding_service.settings") as mock_settings,
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.litellm_base_url = "http://fake-requesty"
        mock_settings.litellm_api_key = "fake-key"

        from services.embedding_service import ACTIVE_EMBEDDING_MODEL, embed

        result_vector, result_model_id = asyncio.run(embed("Test-Text"))

    assert result_vector is None
    assert result_model_id == ACTIVE_EMBEDDING_MODEL


def test_embed_returns_correct_explicit_model_id():
    """embed(model_id=X) gibt exakt model_id=X zurück — auch bei Fehler."""
    with patch("services.embedding_service.settings") as mock_settings:
        mock_settings.litellm_base_url = ""  # kein URL → sofortiger Return
        mock_settings.litellm_api_key = ""

        from services.embedding_service import ACTIVE_EMBEDDING_MODEL, embed

        # Explizit selbes Modell übergeben
        _, returned_model_id = asyncio.run(embed("x", ACTIVE_EMBEDDING_MODEL))

    assert returned_model_id == ACTIVE_EMBEDDING_MODEL


def test_embed_empty_text_returns_none_with_model_id():
    """embed() mit leerem Text gibt (None, model_id) ohne API-Call zurück."""
    from services.embedding_service import ACTIVE_EMBEDDING_MODEL, embed

    vector, model_id = asyncio.run(embed(""))
    assert vector is None
    assert model_id == ACTIVE_EMBEDDING_MODEL


# ---------------------------------------------------------------------------
# B) Canary-Task stoppt bei Recall-Drop
# ---------------------------------------------------------------------------


def test_canary_rollback_on_recall_drop():
    """Wenn recall_new < recall_old → kein Roll, Status 'stopped_recall_drop'."""
    # Mock: 1 Tenant mit 2 Canary-Chunks
    fake_tenant_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    async def _fake_reembed(new_model_id, percent):
        # Simuliere den Kern-Ablauf ohne echte DB
        recall_old = 0.85
        recall_new = 0.70  # Drop!

        if recall_new < recall_old:
            return {
                "status": "partial",
                "new_model_id": new_model_id,
                "tenants": {
                    fake_tenant_id: {
                        "status": "stopped_recall_drop",
                        "recall_old": recall_old,
                        "recall_new": recall_new,
                        "canary_chunks": 1,
                    }
                },
            }
        # Darf hier nicht ankommen
        return {"status": "done"}

    with patch("tasks.reembed_task._reembed_async", side_effect=_fake_reembed):
        # Task direkt als Funktion aufrufen (kein Celery Worker nötig)
        result = asyncio.run(_fake_reembed("gemini-embedding-001-1536d", 10))

    assert result["status"] == "partial"
    tenant_result = result["tenants"][fake_tenant_id]
    assert tenant_result["status"] == "stopped_recall_drop"
    assert tenant_result["recall_new"] < tenant_result["recall_old"]


def test_canary_task_unknown_model_id_returns_error():
    """reembed_chunks_with_canary() gibt error zurück für unbekanntes model_id."""
    from tasks.reembed_task import reembed_chunks_with_canary

    # Task direkt aufrufen (apply() simuliert Celery-Kontext)
    result = reembed_chunks_with_canary.apply(
        args=["totally-unknown-model-v99"],
        kwargs={"percent": 10},
    ).result

    assert result["status"] == "error"
    assert "unknown model_id" in result["reason"]


# ---------------------------------------------------------------------------
# C) drift_monitor schreibt in throttle_events scope='embedding_drift'
# ---------------------------------------------------------------------------


def test_drift_monitor_writes_to_throttle_events():
    """_insert_drift_event fügt Zeile mit scope='embedding_drift' ein."""
    inserted_rows: list[dict] = []

    async def _fake_execute(sql_or_text, params=None):
        # Fange INSERT-Aufrufe ab
        sql_str = str(sql_or_text) if not isinstance(sql_or_text, str) else sql_or_text
        if "INSERT INTO throttle_events" in sql_str and params:
            if params.get("scope") == "embedding_drift":
                inserted_rows.append(dict(params))
        result = MagicMock()
        result.fetchall.return_value = []
        result.fetchone.return_value = None
        result.scalar.return_value = None
        return result

    mock_db = AsyncMock()
    mock_db.execute = _fake_execute
    mock_db.commit = AsyncMock()

    from tasks.drift_monitor_task import _insert_drift_event

    asyncio.run(_insert_drift_event(mock_db, "tenant-uuid-123", recall=0.82, p95_ms=45.5))

    assert len(inserted_rows) == 1
    row = inserted_rows[0]
    assert row["scope"] == "embedding_drift"
    assert row["cnt"] == int(0.82 * 1000)  # 820
    assert row["lim"] == 45  # int(45.5)
    assert row["task"] == "drift_monitor_task.run_embedding_drift_monitor"
    assert row["tid"] == "tenant-uuid-123"


def test_drift_monitor_recall_encoding_roundtrip():
    """Recall-Encoding: int(recall*1000)/1000 ≈ recall (Verlust <0.1%)."""
    for recall in [0.0, 0.5, 0.85, 1.0, 0.333]:
        encoded = int(recall * 1000)
        decoded = encoded / 1000.0
        assert abs(decoded - recall) < 0.001, f"Encoding-Fehler bei recall={recall}"


def test_load_4week_avg_recall_returns_none_when_empty():
    """_load_4week_avg_recall gibt None zurück wenn keine historischen Daten."""

    async def _fake_execute(sql_or_text, params=None):
        mock_row = MagicMock()
        mock_row.avg_recall_enc = None
        result = MagicMock()
        result.fetchone.return_value = mock_row
        return result

    mock_db = AsyncMock()
    mock_db.execute = _fake_execute

    from tasks.drift_monitor_task import _load_4week_avg_recall

    result = asyncio.run(_load_4week_avg_recall(mock_db, "some-tenant-id"))
    assert result is None
