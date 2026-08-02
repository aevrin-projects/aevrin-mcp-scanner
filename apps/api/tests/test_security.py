from __future__ import annotations

import time

import jwt
import pytest
from fastapi import HTTPException

from aevrin_api.security import decode_supabase_jwt, generate_api_key, hash_api_key


def test_decode_valid_supabase_jwt(settings):
    payload = {
        "sub": "user-123",
        "email": "test@example.com",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")
    user = decode_supabase_jwt(token, settings)
    assert user.id == "user-123"
    assert user.email == "test@example.com"


def test_decode_rejects_wrong_secret(settings):
    token = jwt.encode(
        {"sub": "user-123", "aud": "authenticated", "exp": int(time.time()) + 3600},
        "wrong-secret",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_supabase_jwt(token, settings)
    assert exc_info.value.status_code == 401


def test_decode_rejects_expired_token(settings):
    token = jwt.encode(
        {"sub": "user-123", "aud": "authenticated", "exp": int(time.time()) - 10},
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException):
        decode_supabase_jwt(token, settings)


def test_api_key_hash_is_deterministic_for_verification():
    plaintext, stored_hash = generate_api_key("pepper")
    assert hash_api_key(plaintext, "pepper") == stored_hash


def test_api_key_hash_differs_with_different_pepper():
    plaintext, stored_hash = generate_api_key("pepper-a")
    assert hash_api_key(plaintext, "pepper-b") != stored_hash


def test_api_key_plaintext_never_equals_hash():
    plaintext, stored_hash = generate_api_key("pepper")
    assert plaintext != stored_hash
    assert plaintext.startswith("aevrin_")
