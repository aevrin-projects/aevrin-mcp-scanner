from __future__ import annotations

import hashlib
import hmac
import secrets
from functools import lru_cache

import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient

from aevrin_api.config import Settings

# Supabase projects can rotate between the legacy HS256 shared-secret scheme
# and the current asymmetric signing keys (ECC/RSA), a project mid-rotation
# has tokens signed under both. Verifying against the JWKS endpoint (which
# PyJWKClient caches) picks the right public key per-token by its `kid`
# header, so this works across rotation without us tracking which scheme is
# "current" ourselves, and never requires a shared secret at all.
_SUPPORTED_ALGORITHMS = ["ES256", "RS256", "HS256"]


class AuthenticatedUser:
    __slots__ = ("email", "id")

    def __init__(self, id: str, email: str | None):
        self.id = id
        self.email = email


@lru_cache
def _jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=300)


def decode_supabase_jwt(token: str, settings: Settings) -> AuthenticatedUser:
    """Verifies a Supabase Auth access token against the project's JWKS
    endpoint, supports both current asymmetric signing keys and any
    legacy HS256 tokens still valid during a key rotation window."""
    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=_SUPPORTED_ALGORITHMS,
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return AuthenticatedUser(id=user_id, email=payload.get("email"))


def generate_api_key(pepper: str) -> tuple[str, str]:
    """Returns (plaintext_key_shown_once, hash_to_store).

    API keys are 256 bits of random entropy, not human-chosen passwords;
    Argon2/bcrypt-style slow hashing is the wrong tool here (it exists to
    resist brute-forcing *low*-entropy secrets, and it's not lookup-able,
    which would force a full-table scan per request). A keyed HMAC-SHA256
    over the token is fast, directly indexable with a UNIQUE constraint,
    and just as unforgeable given the server-side pepper stays secret.
    """
    plaintext = f"aevrin_{secrets.token_urlsafe(32)}"
    return plaintext, hash_api_key(plaintext, pepper)


def hash_api_key(plaintext: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), plaintext.encode(), hashlib.sha256).hexdigest()
