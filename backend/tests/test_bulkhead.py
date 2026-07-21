"""Tests für den Tenant-Bulkhead (W5). Gemockte Session — keine echte DB."""

from unittest.mock import MagicMock

import pytest

from services.bulkhead import BulkheadFull, _acquire, _max_concurrent, tenant_slot


def _session_returning(acquire_row):
    """Mock-Session: erster execute()-Call (INSERT..RETURNING) liefert acquire_row."""
    session = MagicMock()
    result = MagicMock()
    result.first.return_value = acquire_row
    session.execute.return_value = result
    return session


def test_acquire_success_when_under_limit():
    # RETURNING active liefert eine Row → Slot vergeben.
    session = _session_returning(MagicMock())
    assert _acquire(session, "tenant-a") is True
    session.commit.assert_called()


def test_acquire_fails_when_full():
    # Kein RETURNING (WHERE active < lim greift nicht) → None → Slot voll.
    session = _session_returning(None)
    assert _acquire(session, "tenant-a") is False


def test_tenant_slot_raises_when_full():
    session = _session_returning(None)
    with pytest.raises(BulkheadFull):
        with tenant_slot(session, "tenant-a"):
            pass  # sollte nie erreicht werden


def test_tenant_slot_releases_after_use():
    session = _session_returning(MagicMock())
    with tenant_slot(session, "tenant-a"):
        pass
    # acquire (INSERT) + release (UPDATE) → mind. 2 execute-Calls.
    assert session.execute.call_count >= 2


def test_max_concurrent_default_positive():
    assert _max_concurrent() >= 1
