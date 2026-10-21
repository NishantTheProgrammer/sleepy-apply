import os
import pytest
from app.security.vault import encrypt, decrypt
from app.security.jwt import create_access_token, decode_token


def test_encryption_roundtrip():
    secret = "sk-ant-api-test-key-12345"
    encrypted = encrypt(secret)
    assert encrypted != secret
    assert len(encrypted) > 20

    decrypted = decrypt(encrypted)
    assert decrypted == secret


def test_empty_encryption():
    assert encrypt(None) is None
    assert decrypt(None) is None
    assert encrypt("") == ""
    assert decrypt("") == ""


def test_jwt_create_and_verify():
    user_id = "650c1f1e1f1e1f1e1f1e1f1e"
    token = create_access_token({"sub": user_id, "role": "user"})
    assert isinstance(token, str)

    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["role"] == "user"
