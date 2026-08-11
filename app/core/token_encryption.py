from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings, get_settings


class TokenDecryptionError(Exception):
    pass


@lru_cache
def _fernet_for_key(key: str) -> Fernet:
    return Fernet(key.encode())


def get_fernet(settings: Settings | None = None) -> Fernet:
    resolved = settings or get_settings()
    return _fernet_for_key(resolved.token_encryption_key)


def encrypt_token(plaintext: str, *, settings: Settings | None = None) -> str:
    return get_fernet(settings).encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str, *, settings: Settings | None = None) -> str:
    try:
        return get_fernet(settings).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise TokenDecryptionError("Stored OAuth token is not valid ciphertext") from exc


def ensure_token_encrypted(value: str, *, settings: Settings | None = None) -> str:
    try:
        decrypt_token(value, settings=settings)
    except TokenDecryptionError:
        return encrypt_token(value, settings=settings)
    return value
