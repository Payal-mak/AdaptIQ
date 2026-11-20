from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, require_roles
from app.models.enums import Role
from app.models.user import User
from app.schemas.user import AdminUserCreate, UserOut, UserUpdate
from app.services import user_service

# Every route in this file is admin-only.
router = APIRouter(
    prefix="/users",
    tags=["users (admin)"],
)
AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: AdminUserCreate, db: DbSession, _admin: AdminUser) -> UserOut:
    """Create a user with any role (e.g. faculty accounts)."""
    try:
        user = user_service.create_user(db, data.email, data.full_name, data.password, data.role)
    except user_service.EmailAlreadyExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    return UserOut.model_validate(user)


@router.get("", response_model=list[UserOut])
def list_users(db: DbSession, _admin: AdminUser, role: Role | None = None) -> list[UserOut]:
    query = select(User).order_by(User.id)
    if role is not None:
        query = query.where(User.role == role)
    return [UserOut.model_validate(u) for u in db.scalars(query)]


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: DbSession, admin: AdminUser) -> UserOut:
    """Change a user's role or active flag. Admins cannot lock themselves out."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        if data.is_active is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate yourself")
        if data.role is not None and data.role != Role.ADMIN:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin role")
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
