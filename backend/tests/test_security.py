from datetime import timedelta

import jwt
import pytest

from app.core.config import get_settings, validate_jwt_secret
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.enums import Role


def test_hash_is_not_plain_text_and_verifies() -> None:
    hashed = hash_password("my-secret-pw")
    assert hashed != "my-secret-pw"
    assert "my-secret-pw" not in hashed
    assert verify_password("my-secret-pw", hashed)
    assert not verify_password("wrong", hashed)


def test_same_password_gets_different_hashes() -> None:
    assert hash_password("same-password") != hash_password("same-password")  # random salt


def test_token_contains_sub_role_exp() -> None:
    payload = decode_access_token(create_access_token(7, Role.FACULTY))
    assert payload["sub"] == "7"
    assert payload["role"] == "faculty"
    assert "exp" in payload


def test_expired_token_rejected() -> None:
    token = create_access_token(1, Role.STUDENT, expires_delta=timedelta(seconds=-5))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_signed_with_other_secret_rejected() -> None:
    forged = jwt.encode(
        {"sub": "1", "role": "admin", "exp": 9999999999},
        "another-secret-another-secret-123456",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)


@pytest.mark.parametrize(
    "bad", ["", "   ", "short", "change-me-to-a-long-random-string", "change-me" + "x" * 40]
)
def test_weak_jwt_secrets_refused(bad: str) -> None:
    with pytest.raises(RuntimeError):
        validate_jwt_secret(bad)


def test_good_jwt_secret_accepted() -> None:
    validate_jwt_secret(get_settings().jwt_secret)


def test_app_refuses_to_start_with_placeholder_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(get_settings(), "jwt_secret", "change-me-to-a-long-random-string")
    with pytest.raises(RuntimeError, match="placeholder"):
        with TestClient(app):  # entering the context runs the startup (lifespan) code
            pass
