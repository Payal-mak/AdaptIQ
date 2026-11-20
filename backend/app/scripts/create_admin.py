"""Create the first admin account: python -m app.scripts.create_admin"""

import getpass
import sys

from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_engine
from app.models.enums import Role
from app.schemas.user import AdminUserCreate
from app.services import user_service


def create_admin(db: Session, email: str, full_name: str, password: str) -> None:
    """Validate the input and create an admin. Raises EmailAlreadyExistsError / ValidationError."""
    data = AdminUserCreate(email=email, full_name=full_name, password=password, role=Role.ADMIN)
    user_service.create_user(db, data.email, data.full_name, data.password, Role.ADMIN)


def main() -> None:
    email = input("Admin email: ").strip()
    full_name = input("Full name: ").strip()
    password = getpass.getpass("Password (hidden, min 8 chars): ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")

    with sessionmaker(bind=get_engine())() as db:
        try:
            create_admin(db, email, full_name, password)
        except user_service.EmailAlreadyExistsError:
            sys.exit(f"A user with email {email.lower()} already exists. Nothing was changed.")
        except ValueError as exc:  # pydantic ValidationError is a ValueError
            sys.exit(f"Invalid input: {exc}")
    print(f"Admin created: {email.lower()}")


if __name__ == "__main__":
    main()
