from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.core.token_encryption import (
    TokenDecryptionError,
    decrypt_token,
    encrypt_token,
    ensure_token_encrypted,
)


@pytest.fixture
def encryption_settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://devplanet:devplanet@127.0.0.1:5432/devplanet",
        github_oauth_client_id="test-oauth-client-id",
        github_oauth_client_secret="test-oauth-client-secret",
        oauth_callback_url="http://test/api/v1/auth/github/callback",
        jwt_secret_key="unit-test-jwt-secret-key-32-bytes-min",
        token_encryption_key=Fernet.generate_key().decode(),
        s3_access_key="devplanet",
        s3_secret_key="devplanet",
    )


def test_encrypt_decrypt_round_trip(encryption_settings: Settings) -> None:
    plaintext = "gho_test_oauth_token_value"
    ciphertext = encrypt_token(plaintext, settings=encryption_settings)
    assert ciphertext != plaintext
    assert decrypt_token(ciphertext, settings=encryption_settings) == plaintext


def test_decrypt_invalid_ciphertext_raises(encryption_settings: Settings) -> None:
    with pytest.raises(TokenDecryptionError):
        decrypt_token("not-a-fernet-token", settings=encryption_settings)


def test_decrypt_with_wrong_key_raises(encryption_settings: Settings) -> None:
    ciphertext = encrypt_token("gho_test", settings=encryption_settings)
    other_settings = encryption_settings.model_copy(
        update={"token_encryption_key": Fernet.generate_key().decode()},
    )
    with pytest.raises(TokenDecryptionError):
        decrypt_token(ciphertext, settings=other_settings)


def test_ensure_token_encrypted_idempotent(encryption_settings: Settings) -> None:
    plaintext = "gho_legacy_token"
    first = ensure_token_encrypted(plaintext, settings=encryption_settings)
    assert first != plaintext
    assert ensure_token_encrypted(first, settings=encryption_settings) == first
