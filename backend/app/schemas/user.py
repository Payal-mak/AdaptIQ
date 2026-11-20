from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

from app.models.enums import Role


def _clean_email(value: object) -> object:
    """Trim spaces and lowercase before the email is validated."""
    return value.strip().lower() if isinstance(value, str) else value


CleanEmail = Annotated[EmailStr, BeforeValidator(_clean_email)]
Password = Annotated[str, Field(min_length=8, max_length=128)]


class UserCreate(BaseModel):
    """Self-registration. There is deliberately NO role field: extra fields are ignored."""

    email: CleanEmail
    full_name: Annotated[str, Field(min_length=1, max_length=255)]
    password: Password


class AdminUserCreate(UserCreate):
    """Admin creates a user with any role."""

    role: Role = Role.STUDENT


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    """What the API returns about a user. Never includes password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
