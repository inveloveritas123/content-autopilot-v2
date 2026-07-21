"""Tests für tasks.deletion_purge_task._delete_nc_files (W6-Härtung, #156-followup).

Vorher: Stub (kein-op, nur Log). Jetzt: löscht die tenant-spezifischen
NC-Pfade (nc_transcript_path, nc_analysis_path, nc_content_path aus
tenants.settings) via services.nextcloud.nextcloud_client.

Alle DB-Zugriffe (_tenant_nc_paths) und NC-Calls (nextcloud_client) werden
gemockt — kein echter Netzwerk-/DB-Call.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from tasks.deletion_purge_task import (
    _delete_nc_files,
    _delete_nc_files_async,
    _tenant_nc_paths,
)


def _mock_db_with_settings(settings: dict | None):
    """Baut einen sync_session_factory()-Kontextmanager-Mock, dessen
    execute(...).fetchone() eine Row mit .settings liefert."""
    row = MagicMock()
    row.settings = settings
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.execute.return_value.fetchone.return_value = row if settings is not None else None
    return mock_db


class TestTenantNcPaths:
    def test_returns_configured_paths(self):
        mock_db = _mock_db_with_settings(
            {
                "nc_transcript_path": "/z/Transkripte",
                "nc_analysis_path": "/z/Analysen",
                "nc_content_path": "/z/Content",
            }
        )
        with patch(
            "tasks.deletion_purge_task.sync_session_factory", return_value=mock_db
        ):
            paths = _tenant_nc_paths("tenant-1")

        assert paths == ["/z/Transkripte", "/z/Analysen", "/z/Content"]

    def test_missing_settings_returns_empty(self):
        mock_db = _mock_db_with_settings(None)
        with patch(
            "tasks.deletion_purge_task.sync_session_factory", return_value=mock_db
        ):
            paths = _tenant_nc_paths("tenant-unknown")

        assert paths == []

    def test_partial_settings_only_returns_set_keys(self):
        mock_db = _mock_db_with_settings({"nc_transcript_path": "/z/Transkripte"})
        with patch(
            "tasks.deletion_purge_task.sync_session_factory", return_value=mock_db
        ):
            paths = _tenant_nc_paths("tenant-2")

        assert paths == ["/z/Transkripte"]

    def test_db_error_returns_empty_no_raise(self):
        with patch(
            "tasks.deletion_purge_task.sync_session_factory",
            side_effect=RuntimeError("DB down"),
        ):
            paths = _tenant_nc_paths("tenant-3")

        assert paths == []


class TestDeleteNcFilesAsync:
    def test_no_paths_configured_is_noop(self):
        with patch("tasks.deletion_purge_task._tenant_nc_paths", return_value=[]):
            errors = _run(_delete_nc_files_async("tenant-1", "req-1"))
        assert errors == []

    def test_deletes_each_configured_path(self):
        fake_nc = MagicMock()
        fake_nc.list_files_recursive = AsyncMock(return_value=[{"path": "a"}, {"path": "b"}])
        fake_nc.delete_file = AsyncMock(return_value=True)

        with (
            patch(
                "tasks.deletion_purge_task._tenant_nc_paths",
                return_value=["/z/Transkripte", "/z/Analysen"],
            ),
            patch("services.nextcloud.nextcloud_client", fake_nc),
        ):
            errors = _run(_delete_nc_files_async("tenant-1", "req-1"))

        assert errors == []
        assert fake_nc.delete_file.call_count == 2
        fake_nc.delete_file.assert_any_call("/z/Transkripte")
        fake_nc.delete_file.assert_any_call("/z/Analysen")

    def test_nc_unreachable_collects_error_does_not_raise(self):
        fake_nc = MagicMock()
        fake_nc.list_files_recursive = AsyncMock(side_effect=ConnectionError("NC down"))
        fake_nc.delete_file = AsyncMock(return_value=True)

        with (
            patch(
                "tasks.deletion_purge_task._tenant_nc_paths",
                return_value=["/z/Transkripte"],
            ),
            patch("services.nextcloud.nextcloud_client", fake_nc),
        ):
            errors = _run(_delete_nc_files_async("tenant-1", "req-1"))

        assert len(errors) == 1
        assert "NC down" in errors[0] or "list_folder" in errors[0]
        fake_nc.delete_file.assert_not_called()

    def test_delete_failure_collects_error(self):
        fake_nc = MagicMock()
        fake_nc.list_files_recursive = AsyncMock(return_value=[])
        fake_nc.delete_file = AsyncMock(return_value=False)

        with (
            patch(
                "tasks.deletion_purge_task._tenant_nc_paths",
                return_value=["/z/Content"],
            ),
            patch("services.nextcloud.nextcloud_client", fake_nc),
        ):
            errors = _run(_delete_nc_files_async("tenant-1", "req-1"))

        assert len(errors) == 1
        assert "/z/Content" in errors[0]


class TestDeleteNcFilesSync:
    def test_sync_wrapper_returns_async_result(self):
        with patch(
            "tasks.deletion_purge_task._delete_nc_files_async",
            new=AsyncMock(return_value=[]),
        ):
            errors = _delete_nc_files("tenant-1", "req-1")
        assert errors == []

    def test_sync_wrapper_never_raises_on_unexpected_error(self):
        async def _boom(*a, **kw):
            raise RuntimeError("boom")

        with patch("tasks.deletion_purge_task._delete_nc_files_async", new=_boom):
            errors = _delete_nc_files("tenant-1", "req-1")
        assert len(errors) == 1
        assert "boom" in errors[0]


def _run(coro):
    import asyncio

    return asyncio.run(coro)
