"""Envelope encryption for BYOK model API keys (accounts.byok_key_encrypted).

Fernet, not a bespoke scheme: it's authenticated (tamper-evident) symmetric
encryption from a well-reviewed library, which is all this needs: one
server-held key (BYOK_ENCRYPTION_KEY), one column of ciphertext per account.
No key rotation support here, matching every other single-secret env var in
this codebase (config.py); add rotation if/when that's actually needed.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from aevrin_api.config import Settings


class ByokUnavailable(Exception):
    pass


def encrypt_byok_key(settings: Settings, plaintext_key: str) -> str:
    if not settings.byok_encryption_key:
        raise ByokUnavailable("BYOK_ENCRYPTION_KEY is not configured")
    return Fernet(settings.byok_encryption_key.encode()).encrypt(plaintext_key.encode()).decode()


def decrypt_byok_key(settings: Settings, ciphertext: str) -> str | None:
    """None on any failure (bad/rotated key, corrupt data); a BYOK call
    that can't decrypt its key must fail open to the pooled key, exactly
    like every other triage failure mode in triage.py, not 500."""
    if not settings.byok_encryption_key:
        return None
    try:
        return Fernet(settings.byok_encryption_key.encode()).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return None
