from __future__ import annotations

from app.models.types.encrypted_string import EncryptedString


def test_encrypted_string_bind_and_result_round_trip() -> None:
    column = EncryptedString()
    plaintext = "gho_user_token"
    stored = column.process_bind_param(plaintext, dialect=object())
    assert stored is not None
    assert stored != plaintext
    assert column.process_result_value(stored, dialect=object()) == plaintext


def test_encrypted_string_none_passthrough() -> None:
    column = EncryptedString()
    assert column.process_bind_param(None, dialect=object()) is None
    assert column.process_result_value(None, dialect=object()) is None
