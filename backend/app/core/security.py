from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.models.enums import Role

JWT_ALGORITHM = "HS256"

# Argon2 is the recommended modern password hash (salted, deliberately slow).
_hasher = PasswordHash.recommended()

# Hash of a throwaway password; used to spend the same time when an email is unknown.
DUMMY_HASH: str = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    """Return a salted Argon2 hash. The plain password is never stored."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against a stored hash."""
    return _hasher.verify(password, password_hash)


def create_access_token(user_id: int, role: Role, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT carrying the user id (sub), role and expiry (exp)."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=get_settings().access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role.value,
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify signature and expiry, return the payload. Raises jwt.PyJWTError if invalid."""
    return jwt.decode(
        token,
        get_settings().jwt_secret,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
