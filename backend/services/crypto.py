"""Generic, reusable secret encryption helpers.

Provides Fernet-based encrypt/decrypt/mask functions that derive a per-domain
key from DEFAULT_TENANT_KEY + a caller-supplied salt string.

Usage example (Telegram tokens):
    from services.crypto import encrypt_secret, decrypt_secret, mask_secret

    token_enc = encrypt_secret(raw_token, salt="-telegram-encrypt")
    raw_token  = decrypt_secret(token_enc, salt="-telegram-encrypt")
    display    = mask_secret(raw_token)

Intentionally does NOT import from api.llm_settings (which pulls FastAPI) and
does NOT add any new environment variables — DEFAULT_TENANT_KEY is sufficient.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from config import settings as _app_settings


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fernet_for(salt: str) -> Fernet:
    """Return a Fernet instance whose key is derived from DEFAULT_TENANT_KEY + salt."""
    key_material = hashlib.sha256(
        (_app_settings.default_tenant_key + salt).encode()
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encrypt_secret(plaintext: str, *, salt: str) -> str:
    """Encrypt *plaintext* with a salt-specific Fernet key.

    Returns the Fernet token as a plain str (URL-safe base64, no newlines).
    The result is deterministically decryptable only with the same salt and
    DEFAULT_TENANT_KEY value.
    """
    f = _fernet_for(salt)
    return f.encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str, *, salt: str) -> str:
    """Decrypt a Fernet *token* produced by :func:`encrypt_secret`.

    Fault-tolerant: returns ``""`` on any decryption error (wrong salt, wrong
    key, corrupted token, empty input) instead of raising.
    """
    if not token:
        return ""
    try:
        f = _fernet_for(salt)
        return f.decrypt(token.encode()).decode()
    except (InvalidToken, Exception):
        return ""


def mask_secret(plaintext: str | None) -> str | None:
    """Return a partially-masked representation of *plaintext*.

    - ``None``         → ``None``
    - ``""``           → ``None``
    - len ≤ 8          → ``"***"``
    - otherwise        → ``"<first4>...<last4>"``
    """
    if not plaintext:
        return None
    if len(plaintext) <= 8:
        return "***"
    return plaintext[:4] + "..." + plaintext[-4:]
