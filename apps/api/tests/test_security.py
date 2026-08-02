from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

import aevrin_api.security as security_module
from aevrin_api.security import decode_supabase_jwt, generate_api_key, hash_api_key


@pytest.fixture
def ec_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


@pytest.fixture(autouse=True)
def _clear_jwk_client_cache():
    security_module._jwk_client.cache_clear()
    yield
    security_module._jwk_client.cache_clear()


def _mock_jwks(monkeypatch, public_key):
    """decode_supabase_jwt fetches the verification key from Supabase's
    JWKS endpoint (see security.py) — tests stub that lookup rather than
    hitting the network, while still exercising the real jwt.decode call
    with a real ES256-signed token."""
    fake_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key)
    )
    monkeypatch.setattr(security_module, "_jwk_client", lambda jwks_url: fake_client)


def test_decode_valid_supabase_jwt(settings, ec_keypair, monkeypatch):
    private_key, public_key = ec_keypair
    _mock_jwks(monkeypatch, public_key)
    payload = {
        "sub": "user-123",
        "email": "test@example.com",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, private_key, algorithm="ES256")
    user = decode_supabase_jwt(token, settings)
    assert user.id == "user-123"
    assert user.email == "test@example.com"


def test_decode_rejects_token_signed_by_a_different_key(settings, ec_keypair, monkeypatch):
    _, public_key = ec_keypair
    _mock_jwks(monkeypatch, public_key)
    other_private_key = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(
        {"sub": "user-123", "aud": "authenticated", "exp": int(time.time()) + 3600},
        other_private_key,
        algorithm="ES256",
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_supabase_jwt(token, settings)
    assert exc_info.value.status_code == 401


def test_decode_rejects_expired_token(settings, ec_keypair, monkeypatch):
    private_key, public_key = ec_keypair
    _mock_jwks(monkeypatch, public_key)
    token = jwt.encode(
        {"sub": "user-123", "aud": "authenticated", "exp": int(time.time()) - 10},
        private_key,
        algorithm="ES256",
    )
    with pytest.raises(HTTPException):
        decode_supabase_jwt(token, settings)


def test_decode_rejects_wrong_audience(settings, ec_keypair, monkeypatch):
    private_key, public_key = ec_keypair
    _mock_jwks(monkeypatch, public_key)
    token = jwt.encode(
        {"sub": "user-123", "aud": "some-other-audience", "exp": int(time.time()) + 3600},
        private_key,
        algorithm="ES256",
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
