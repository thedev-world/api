from __future__ import annotations

from app.core.token_encryption import decrypt_token, encrypt_token
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


class EncryptedString(TypeDecorator[str | None]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        if value is None:
            return None
        return encrypt_token(value)

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        if value is None:
            return None
        return decrypt_token(value)
