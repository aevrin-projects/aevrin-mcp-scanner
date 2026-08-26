from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from aevrin_api.utils.crypto import EncryptionUnavailable, decrypt_secret, encrypt_secret


def test_encrypt_then_decrypt_roundtrips(settings):
    settings = settings.model_copy(update={"byok_encryption_key": Fernet.generate_key().decode()})
    ciphertext = encrypt_secret(settings, "sk-real-secret-value")
    assert ciphertext != "sk-real-secret-value"
    assert decrypt_secret(settings, ciphertext) == "sk-real-secret-value"


def test_encrypt_raises_when_unconfigured(settings):
    with pytest.raises(EncryptionUnavailable):
        encrypt_secret(settings, "sk-real-secret-value")


def test_decrypt_fails_open_to_none_when_unconfigured(settings):
    assert decrypt_secret(settings, "anything") is None


def test_decrypt_fails_open_to_none_on_wrong_key(settings):
    encrypting_settings = settings.model_copy(update={"byok_encryption_key": Fernet.generate_key().decode()})
    ciphertext = encrypt_secret(encrypting_settings, "sk-real-secret-value")

    decrypting_settings = settings.model_copy(update={"byok_encryption_key": Fernet.generate_key().decode()})
    assert decrypt_secret(decrypting_settings, ciphertext) is None
