from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import DUMMY_HASH, hash_password, verify_password
from app.models.enums import Role
from app.models.user import User


class EmailAlreadyExistsError(Exception):
    """Raised when creating a user whose email is already registered."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def create_user(db: Session, email: str, full_name: str, password: str, role: Role) -> User:
    """Create a user with a hashed password. Raises EmailAlreadyExistsError on duplicates."""
    email = normalize_email(email)
    if get_by_email(db, email) is not None:
        raise EmailAlreadyExistsError(email)
    user = User(email=email, full_name=full_name.strip(), password_hash=hash_password(password), role=role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # two requests registered the same email at once
        db.rollback()
        raise EmailAlreadyExistsError(email) from exc
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the user if the email/password are right and the account is active, else None."""
    user = get_by_email(db, email)
    if user is None:
        verify_password(password, DUMMY_HASH)  # same work as a real check, hides which emails exist
        return None
    if not verify_password(password, user.password_hash) or not user.is_active:
        return None
    return user


def email_domain_allowed(email: str, allowed_domain: str) -> bool:
    """True if no restriction is set, or the email ends with @<allowed_domain>."""
    allowed = allowed_domain.strip().lower().lstrip("@")
    if not allowed:
        return True
    return normalize_email(email).endswith("@" + allowed)
