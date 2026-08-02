from __future__ import annotations

import hashlib
import hmac
import secrets

import jwt
from fastapi import HTTPException, status

from .config import Settings


class AuthenticatedUser:
    __slots__ = ("email", "id")

    def __init__(self, id: str, email: str | None):
        self.id = id
        self.email = email


def decode_supabase_jwt(token: str, settings: Settings) -> AuthenticatedUser:
    """Verifies a Supabase Auth access token (HS256, shared JWT secret)."""
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
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

    API keys are 256 bits of random entropy, not human-chosen passwords —
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
