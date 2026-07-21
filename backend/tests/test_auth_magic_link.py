"""Unit-Tests für den passwortlosen Magic-Link-Auth-Flow (W3, services/auth.py).

Strategie: services/auth.py hat außer `config.settings` keine schweren
Abhängigkeiten (stdlib hashlib/hmac/secrets/smtplib) — die Suite importiert es
daher direkt (kein sys.modules-Stubbing nötig, anders als tests/test_admin_auth.py
für api/admin_auth.py). Für `_session_secret()` wird pro Test `services.auth.settings`
per `patch(...)` auf ein MagicMock mit `admin_session_secret` gesetzt, damit die
Funktion nicht in den production-Gate-RuntimeError läuft (siehe
services/auth.py::_session_secret-Docstring).

Ausführung (lokal):
    cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_auth_magic_link.py -q
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import services.auth as auth_svc


def _fake_settings(**overrides) -> MagicMock:
    """Settings-Mock mit gültigem admin_session_secret (sonst RuntimeError, s.o.)."""
    settings = MagicMock()
    settings.admin_session_secret = "test-secret-32-chars-xxxxxxxxxxxxx"
    settings.app_env = "test"
    settings.default_tenant_key = "test-key"
    settings.smtp_host = None
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


# ---------------------------------------------------------------------------
# generate_magic_token / hash_magic_token
# ---------------------------------------------------------------------------


class TestGenerateMagicToken:
    def test_returns_raw_hash_expires_tuple(self):
        raw, token_hash, expires_at = auth_svc.generate_magic_token()
        assert isinstance(raw, str) and raw
        assert isinstance(token_hash, str) and token_hash
        assert isinstance(expires_at, datetime)

    def test_hash_matches_sha256_of_raw(self):
        raw, token_hash, _ = auth_svc.generate_magic_token()
        assert token_hash == hashlib.sha256(raw.encode()).hexdigest()

    def test_expires_at_is_in_the_future(self):
        _, _, expires_at = auth_svc.generate_magic_token()
        assert expires_at > datetime.now(UTC)

    def test_expires_at_matches_ttl(self):
        before = datetime.now(UTC)
        _, _, expires_at = auth_svc.generate_magic_token()
        after = datetime.now(UTC)
        expected_min = before + timedelta(seconds=auth_svc.MAGIC_LINK_TTL_SECONDS)
        expected_max = after + timedelta(seconds=auth_svc.MAGIC_LINK_TTL_SECONDS)
        assert expected_min <= expires_at <= expected_max

    def test_two_calls_produce_different_tokens(self):
        raw1, hash1, _ = auth_svc.generate_magic_token()
        raw2, hash2, _ = auth_svc.generate_magic_token()
        assert raw1 != raw2
        assert hash1 != hash2


class TestHashMagicToken:
    def test_hash_magic_token_matches_generate(self):
        raw, token_hash, _ = auth_svc.generate_magic_token()
        assert auth_svc.hash_magic_token(raw) == token_hash

    def test_hash_magic_token_is_deterministic(self):
        assert auth_svc.hash_magic_token("same-raw-token") == auth_svc.hash_magic_token(
            "same-raw-token"
        )

    def test_hash_magic_token_differs_for_different_input(self):
        assert auth_svc.hash_magic_token("a") != auth_svc.hash_magic_token("b")


# ---------------------------------------------------------------------------
# send_magic_link_email
# ---------------------------------------------------------------------------


class TestSendMagicLinkEmail:
    def test_no_smtp_host_returns_false_without_crash(self):
        with patch("services.auth.settings", _fake_settings(smtp_host=None)):
            result = auth_svc.send_magic_link_email("user@example.com", "https://x/verify?token=abc")
        assert result is False

    def test_smtp_send_success_returns_true(self):
        with patch("services.auth.settings", _fake_settings(smtp_host="smtp.example.com")):
            with patch("services.auth.smtplib.SMTP") as mock_smtp_cls:
                mock_server = MagicMock()
                mock_smtp_cls.return_value.__enter__.return_value = mock_server
                result = auth_svc.send_magic_link_email(
                    "user@example.com", "https://x/verify?token=abc"
                )
        assert result is True
        mock_server.send_message.assert_called_once()

    def test_smtp_exception_returns_false_without_crash(self):
        with patch("services.auth.settings", _fake_settings(smtp_host="smtp.example.com")):
            with patch("services.auth.smtplib.SMTP", side_effect=OSError("connection refused")):
                result = auth_svc.send_magic_link_email(
                    "user@example.com", "https://x/verify?token=abc"
                )
        assert result is False


# ---------------------------------------------------------------------------
# make_session / verify_session
# ---------------------------------------------------------------------------


class TestSessionRoundtrip:
    def test_make_then_verify_returns_uid(self):
        with patch("services.auth.settings", _fake_settings()):
            token = auth_svc.make_session("user-123")
            uid = auth_svc.verify_session(token)
        assert uid == "user-123"

    def test_token_has_payload_dot_signature_shape(self):
        with patch("services.auth.settings", _fake_settings()):
            token = auth_svc.make_session("user-123")
        assert token.count(".") == 1

    def test_manipulated_signature_returns_none(self):
        with patch("services.auth.settings", _fake_settings()):
            token = auth_svc.make_session("user-123")
            b64, _sig = token.rsplit(".", 1)
            tampered = f"{b64}.deadbeefdeadbeef"
            result = auth_svc.verify_session(tampered)
        assert result is None

    def test_manipulated_payload_returns_none(self):
        import base64
        import json

        with patch("services.auth.settings", _fake_settings()):
            token = auth_svc.make_session("user-123")
            b64, sig = token.rsplit(".", 1)
            padded = b64 + ("=" * ((4 - len(b64) % 4) % 4))
            payload = json.loads(base64.urlsafe_b64decode(padded))
            payload["uid"] = "attacker"
            new_b64 = (
                base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
            )
            tampered = f"{new_b64}.{sig}"
            result = auth_svc.verify_session(tampered)
        assert result is None

    def test_garbage_token_returns_none(self):
        with patch("services.auth.settings", _fake_settings()):
            assert auth_svc.verify_session("not-a-valid-token") is None
            assert auth_svc.verify_session("") is None

    def test_expired_session_returns_none_via_time_patch(self):
        with patch("services.auth.settings", _fake_settings()):
            with patch("services.auth.time") as mock_time:
                mock_time.time.return_value = 1_000_000
                token = auth_svc.make_session("user-123")

            with patch("services.auth.time") as mock_time:
                mock_time.time.return_value = 1_000_000 + auth_svc.SESSION_TTL_SECONDS + 1
                result = auth_svc.verify_session(token)
        assert result is None

    def test_expired_session_returns_none_via_negative_ttl(self):
        """Alternativer Weg zum abgelaufenen Token: SESSION_TTL_SECONDS negativ patchen."""
        with patch("services.auth.settings", _fake_settings()):
            with patch("services.auth.SESSION_TTL_SECONDS", -10):
                token = auth_svc.make_session("user-123")
            result = auth_svc.verify_session(token)
        assert result is None

    def test_session_secret_missing_raises_runtime_error_in_production(self):
        """Ohne admin_session_secret + production + default_tenant_key='default-key' -> RuntimeError."""
        settings = MagicMock()
        settings.admin_session_secret = None
        settings.app_env = "production"
        settings.default_tenant_key = "default-key"
        with patch("services.auth.settings", settings):
            try:
                auth_svc.make_session("user-123")
                raised = False
            except RuntimeError:
                raised = True
        assert raised is True

    def test_session_secret_derivable_outside_production_without_secret(self):
        """Ohne admin_session_secret aber app_env != production -> Ableitung, kein Crash."""
        settings = MagicMock()
        settings.admin_session_secret = None
        settings.app_env = "development"
        settings.default_tenant_key = "some-real-key"
        with patch("services.auth.settings", settings):
            token = auth_svc.make_session("user-123")
            uid = auth_svc.verify_session(token)
        assert uid == "user-123"
