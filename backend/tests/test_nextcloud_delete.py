"""Tests für NextcloudClient.delete_file (W6-Härtung, Issue #156-followup).

DSAR/Recht-auf-Löschung braucht eine WebDAV-DELETE-Methode auf
services.nextcloud.NextcloudClient, damit der Hard-Delete-Cron
(tasks.deletion_purge_task) die tenant-spezifischen NC-Dateien
(Transkripte/Analysen/Content) beim Hard-Delete entfernen kann.

Mockt httpx.AsyncClient — kein echter Netzwerk-Call.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from services.nextcloud import NextcloudClient


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _MockAsyncClient:
    """Minimaler httpx.AsyncClient-Ersatz für 'async with' + .request()."""

    def __init__(self, response: _FakeResponse | None = None, raise_exc: Exception | None = None):
        self._response = response
        self._raise_exc = raise_exc
        self.calls: list[dict] = []

    def __call__(self, *a, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response


class TestNextcloudDeleteFile:
    def test_delete_file_success_204(self):
        """204 No Content → True, DELETE-Methode + korrekte URL verwendet."""
        client = NextcloudClient()
        mock_http = _MockAsyncClient(_FakeResponse(204))
        with patch("services.nextcloud.httpx.AsyncClient", mock_http):
            ok = asyncio.run(client.delete_file("/zukunftsbund/tenant-x/Transkripte"))

        assert ok is True
        assert len(mock_http.calls) == 1
        assert mock_http.calls[0]["method"] == "DELETE"
        assert mock_http.calls[0]["url"].endswith("/zukunftsbund/tenant-x/Transkripte")

    def test_delete_file_already_gone_404_counts_as_success(self):
        """404 (Datei/Ordner existiert schon nicht mehr) ist kein Fehler — idempotent."""
        client = NextcloudClient()
        mock_http = _MockAsyncClient(_FakeResponse(404))
        with patch("services.nextcloud.httpx.AsyncClient", mock_http):
            ok = asyncio.run(client.delete_file("/already/gone"))

        assert ok is True

    def test_delete_file_unexpected_status_returns_false(self):
        """Unerwarteter Status (z.B. 403/500) → False, kein Raise."""
        client = NextcloudClient()
        mock_http = _MockAsyncClient(_FakeResponse(500))
        with patch("services.nextcloud.httpx.AsyncClient", mock_http):
            ok = asyncio.run(client.delete_file("/some/path"))

        assert ok is False

    def test_delete_file_network_error_returns_false_no_raise(self):
        """NC nicht erreichbar (Timeout/ConnectionError) → False, kein Raise.

        Kritisch für den Hard-Delete-Cron: DB-Löschung darf nie an NC scheitern.
        """
        client = NextcloudClient()
        mock_http = _MockAsyncClient(raise_exc=ConnectionError("NC down"))
        with patch("services.nextcloud.httpx.AsyncClient", mock_http):
            ok = asyncio.run(client.delete_file("/unreachable"))

        assert ok is False
