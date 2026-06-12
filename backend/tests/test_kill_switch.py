"""Tests für kill_switch.py"""

from unittest.mock import MagicMock, patch

import pytest

from services.kill_switch import KillSwitchTriggered, check_kill_switch, is_tenant_enabled


def _mock_session_factory(enabled_value):
    """Helper: returns a context manager that yields a mock session."""
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, i: enabled_value
    mock_session = MagicMock()
    mock_session.execute.return_value.fetchone.return_value = mock_row
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_session)
    cm.__exit__ = MagicMock(return_value=False)
    factory = MagicMock(return_value=cm)
    return factory


def test_enabled_tenant_passes():
    with patch("services.kill_switch.sync_session_factory", _mock_session_factory(True)):
        assert is_tenant_enabled("test-tenant-id") is True


def test_disabled_tenant_blocked():
    with patch("services.kill_switch.sync_session_factory", _mock_session_factory(False)):
        assert is_tenant_enabled("test-tenant-id") is False


def test_check_kill_switch_raises_for_disabled():
    with patch("services.kill_switch.sync_session_factory", _mock_session_factory(False)):
        with pytest.raises(KillSwitchTriggered):
            check_kill_switch("test-tenant-id")


def test_check_kill_switch_passes_for_enabled():
    with patch("services.kill_switch.sync_session_factory", _mock_session_factory(True)):
        check_kill_switch("test-tenant-id")  # should not raise


def test_db_failure_fails_open():
    """Bei DB-Fehler: fail-open (Task läuft weiter)."""
    factory = MagicMock(side_effect=Exception("DB down"))
    with patch("services.kill_switch.sync_session_factory", factory):
        assert is_tenant_enabled("test-tenant-id") is True


def test_tenant_not_found_is_disabled():
    """Unbekannter Tenant gilt als disabled."""
    mock_session = MagicMock()
    mock_session.execute.return_value.fetchone.return_value = None
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_session)
    cm.__exit__ = MagicMock(return_value=False)
    factory = MagicMock(return_value=cm)
    with patch("services.kill_switch.sync_session_factory", factory):
        assert is_tenant_enabled("nonexistent") is False
