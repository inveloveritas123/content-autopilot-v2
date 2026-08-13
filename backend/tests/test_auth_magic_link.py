"""Unit-Tests für den Magic-Link- UND den Passwort-Auth-Flow (W3, services/auth.py).

Passwort-Login wurde 2026-08-13 ergänzt (Owner-Entscheid: E-Mail+Passwort statt
Magic-Link als primärer Login). Magic-Link-Endpunkte/-Tests bleiben bestehen
(Fallback-Weg), Datei nicht umbenannt um Diff-Rauschen zu vermeiden.

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


# ---------------------------------------------------------------------------
# hash_password / verify_password (Passwort-Login, 2026-08-13)
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_has_scrypt_prefix_and_three_parts(self):
        h = auth_svc.hash_password("MeinPasswort123")
        parts = h.split("$")
        assert len(parts) == 3
        assert parts[0] == "scrypt"

    def test_correct_password_verifies(self):
        h = auth_svc.hash_password("MeinPasswort123")
        assert auth_svc.verify_password("MeinPasswort123", h) is True

    def test_wrong_password_does_not_verify(self):
        h = auth_svc.hash_password("MeinPasswort123")
        assert auth_svc.verify_password("FalschesPasswort", h) is False

    def test_empty_password_does_not_verify_against_real_hash(self):
        h = auth_svc.hash_password("MeinPasswort123")
        assert auth_svc.verify_password("", h) is False

    def test_two_hashes_of_same_password_differ(self):
        """Zufälliges Salt pro Aufruf — kein Rainbow-Table-Vergleich möglich."""
        h1 = auth_svc.hash_password("gleichesPasswort")
        h2 = auth_svc.hash_password("gleichesPasswort")
        assert h1 != h2
        assert auth_svc.verify_password("gleichesPasswort", h1) is True
        assert auth_svc.verify_password("gleichesPasswort", h2) is True

    def test_malformed_hash_returns_false_without_crash(self):
        assert auth_svc.verify_password("irgendwas", "nicht-scrypt-format") is False
        assert auth_svc.verify_password("irgendwas", "") is False
        assert auth_svc.verify_password("irgendwas", "scrypt$nur-zwei-teile") is False

    def test_wrong_scheme_prefix_returns_false(self):
        h = auth_svc.hash_password("MeinPasswort123")
        _scheme, salt, digest = h.split("$")
        fake = f"bcrypt${salt}${digest}"
        assert auth_svc.verify_password("MeinPasswort123", fake) is False


class TestPasswordHashingSabotageGuard:
    """Sabotage-Gegenprobe (Owner-Auflage 2026-08-13): ein Test MUSS rot werden,
    wenn die Prüfung durch eine kaputte Implementierung ersetzt wird — sonst ist
    der Guard nur eine Behauptung. Diese Klasse hängt hier keinen Produktivcode
    aus (das Repo hat keine Mutation-Testing-Infrastruktur), sondern verifiziert
    die Eigenschaft direkt: eine Fake-Implementierung, die IMMER True zurückgibt
    (der naheliegendste kaputte Zustand — "Login akzeptiert alles"), muss von
    mindestens einem harten Assert oben erkannt werden. Wird diese Testklasse
    selbst durch Auskommentieren der oberen Asserts sabotiert, fällt sie nicht
    auf — sie beweist die Eigenschaft der ECHTEN Funktion, nicht ihre eigene
    Anwesenheit.
    """

    def test_verify_password_is_not_a_stub_that_always_returns_true(self):
        h = auth_svc.hash_password("korrekt")
        # Böswillige/kaputte Implementierung würde hier auch True liefern —
        # dieser Test unterscheidet "prüft echt" von "akzeptiert alles".
        assert auth_svc.verify_password("komplett-falsch", h) is False, (
            "verify_password() akzeptiert ein falsches Passwort — "
            "der Login-Guard wäre wirkungslos."
        )
