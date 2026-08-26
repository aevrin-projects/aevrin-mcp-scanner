"""Envelope encryption for secrets this server holds on a user's behalf.

Today that is exactly one thing: admin TOTP secrets. It was written for
bring-your-own-key model credentials, which no longer exist.

Fernet, not a bespoke scheme: it's authenticated (tamper-evident) symmetric
encryption from a well-reviewed library, which is all this needs: one
server-held key, one column of ciphertext. No key rotation support here,
matching every other single-secret env var in this codebase (config.py).

The env var is still called BYOK_ENCRYPTION_KEY. Renaming it is not a
cosmetic change: the admin TOTP secrets in production are encrypted under
that value, and a rename that failed to carry the value across would lock
every admin out of their own panel. The name is wrong; breaking sign-in to
fix a name is worse.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from aevrin_api.config import Settings


class EncryptionUnavailable(Exception):
    pass


def encrypt_secret(settings: Settings, plaintext: str) -> str:
    if not settings.byok_encryption_key:
        raise EncryptionUnavailable("BYOK_ENCRYPTION_KEY is not configured")
    return Fernet(settings.byok_encryption_key.encode()).encrypt(plaintext.encode()).decode()


def decrypt_secret(settings: Settings, ciphertext: str) -> str | None:
    """None on any failure (bad/rotated key, corrupt data), never a 500.

    The caller decides what an undecryptable secret means. For admin TOTP it
    means the code cannot be verified, which is a refusal, not a bypass."""
    if not settings.byok_encryption_key:
        return None
    try:
        return Fernet(settings.byok_encryption_key.encode()).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return None
