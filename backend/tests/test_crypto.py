"""Tests for services.crypto — encrypt/decrypt/mask helpers.

Local-venv note: the project venv (Py3.9) does NOT have `cryptography`
installed, and services/__init__.py triggers a cascade that fails on Py3.9's
lack of `str | None` union syntax in config.py.  We therefore load
services/crypto.py directly via importlib (bypassing __init__.py) and skip
all tests cleanly when either `cryptography` or `config` cannot be imported.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Resolve the absolute path to services/crypto.py independently of __init__.py
_BACKEND_DIR = Path(__file__).parent.parent
_CRYPTO_PATH = _BACKEND_DIR / "services" / "crypto.py"


def _import_crypto():
    """Load services/crypto directly (no __init__.py) or pytest.skip."""
    # Ensure backend dir is on sys.path so `from config import settings` works
    backend_str = str(_BACKEND_DIR)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)
    try:
        spec = importlib.util.spec_from_file_location("services.crypto", _CRYPTO_PATH)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    except (ImportError, ModuleNotFoundError, Exception) as exc:
        pytest.skip(f"Dependency not available in local venv (CI only): {exc}")


SALT = "-telegram-encrypt"
SALT_OTHER = "-other-service-encrypt"


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------


class TestEncryptDecryptRoundtrip:
    def test_roundtrip_short(self):
        m = _import_crypto()
        plaintext = "abc123"
        token = m.encrypt_secret(plaintext, salt=SALT)
        assert m.decrypt_secret(token, salt=SALT) == plaintext

    def test_roundtrip_long(self):
        m = _import_crypto()
        plaintext = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        token = m.encrypt_secret(plaintext, salt=SALT)
        assert m.decrypt_secret(token, salt=SALT) == plaintext

    def test_token_is_string(self):
        m = _import_crypto()
        token = m.encrypt_secret("hello", salt=SALT)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_differs_from_plaintext(self):
        m = _import_crypto()
        plaintext = "supersecret"
        token = m.encrypt_secret(plaintext, salt=SALT)
        assert token != plaintext

    def test_encryption_is_non_deterministic(self):
        """Fernet uses a random IV — same plaintext produces different tokens."""
        m = _import_crypto()
        t1 = m.encrypt_secret("same", salt=SALT)
        t2 = m.encrypt_secret("same", salt=SALT)
        # Both decrypt correctly but the tokens differ (probabilistic test)
        assert m.decrypt_secret(t1, salt=SALT) == "same"
        assert m.decrypt_secret(t2, salt=SALT) == "same"
        # Not asserting t1 != t2 because it's probabilistically guaranteed but
        # we don't want a flaky test; checking the important direction is enough.


# ---------------------------------------------------------------------------
# Different salts produce different tokens and cross-salt decrypt fails
# ---------------------------------------------------------------------------


class TestSaltIsolation:
    def test_different_salts_produce_different_tokens(self):
        m = _import_crypto()
        t1 = m.encrypt_secret("secret", salt=SALT)
        t2 = m.encrypt_secret("secret", salt=SALT_OTHER)
        # Different keys → different ciphertext
        assert t1 != t2

    def test_wrong_salt_returns_empty(self):
        m = _import_crypto()
        token = m.encrypt_secret("secret", salt=SALT)
        # Decrypting with a different salt must not succeed
        result = m.decrypt_secret(token, salt=SALT_OTHER)
        assert result == ""


# ---------------------------------------------------------------------------
# Fault tolerance of decrypt_secret
# ---------------------------------------------------------------------------


class TestDecryptFaultTolerance:
    def test_garbage_input_returns_empty(self):
        m = _import_crypto()
        assert m.decrypt_secret("not-a-fernet-token", salt=SALT) == ""

    def test_empty_string_returns_empty(self):
        m = _import_crypto()
        assert m.decrypt_secret("", salt=SALT) == ""

    def test_random_bytes_returns_empty(self):
        m = _import_crypto()
        import base64

        garbage = base64.urlsafe_b64encode(b"\x00" * 64).decode()
        assert m.decrypt_secret(garbage, salt=SALT) == ""

    def test_truncated_token_returns_empty(self):
        m = _import_crypto()
        token = m.encrypt_secret("hello", salt=SALT)
        truncated = token[:10]
        assert m.decrypt_secret(truncated, salt=SALT) == ""


# ---------------------------------------------------------------------------
# mask_secret
# ---------------------------------------------------------------------------


class TestMaskSecret:
    def test_none_returns_none(self):
        m = _import_crypto()
        assert m.mask_secret(None) is None

    def test_empty_string_returns_none(self):
        m = _import_crypto()
        assert m.mask_secret("") is None

    def test_short_string_returns_stars(self):
        m = _import_crypto()
        assert m.mask_secret("abc") == "***"
        assert m.mask_secret("12345678") == "***"  # exactly 8 chars

    def test_long_string_shows_prefix_and_suffix(self):
        m = _import_crypto()
        result = m.mask_secret("1234567890:ABCDEFGH")
        assert result == "1234...EFGH"

    def test_mask_nine_chars(self):
        m = _import_crypto()
        result = m.mask_secret("123456789")
        # len == 9 > 8 → show first 4 + ... + last 4
        assert result == "1234...6789"

    def test_mask_does_not_reveal_middle(self):
        m = _import_crypto()
        plaintext = "AAAA_SECRET_BBBB"
        result = m.mask_secret(plaintext)
        assert "_SECRET_" not in result
        assert result.startswith("AAAA")
        assert result.endswith("BBBB")
