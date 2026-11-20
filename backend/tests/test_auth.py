from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.enums import Role
from app.models.user import User
from tests.conftest import PASSWORD, login_headers, make_account

REGISTER = {"email": "Stu@Example.com ", "full_name": "Stu Dent", "password": PASSWORD}


def test_register_works_and_returns_no_password(client: TestClient) -> None:
    response = client.post("/api/auth/register", json=REGISTER)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "stu@example.com"  # trimmed and lowercased
    assert body["role"] == "student"
    assert "password" not in body
    assert "password_hash" not in body


def test_register_ignores_role_in_request(client: TestClient) -> None:
    response = client.post("/api/auth/register", json={**REGISTER, "role": "admin"})
    assert response.status_code == 201
    assert response.json()["role"] == "student"


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post("/api/auth/register", json={**REGISTER, "password": "short"})
    assert response.status_code == 422


def test_duplicate_email_gives_409(client: TestClient) -> None:
    assert client.post("/api/auth/register", json=REGISTER).status_code == 201
    other_case = {**REGISTER, "email": "STU@example.com"}
    assert client.post("/api/auth/register", json=other_case).status_code == 409


def test_email_domain_restriction(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "allowed_email_domain", "college.edu")
    bad = client.post("/api/auth/register", json={**REGISTER, "email": "x@gmail.com"})
    good = client.post("/api/auth/register", json={**REGISTER, "email": "x@college.edu"})
    assert bad.status_code == 400
    assert good.status_code == 201


def test_passwords_are_stored_hashed(client: TestClient, db: Session) -> None:
    client.post("/api/auth/register", json=REGISTER)
    stored = db.scalar(text("SELECT password_hash FROM users WHERE email = 'stu@example.com'"))
    assert stored is not None
    assert stored != PASSWORD
    assert PASSWORD not in stored
    assert stored.startswith("$argon2")


def test_login_success(client: TestClient, db: Session) -> None:
    make_account(db, "a@example.com")
    response = client.post("/api/auth/login", data={"username": "A@example.com", "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_wrong_password_and_unknown_email_give_same_error(client: TestClient, db: Session) -> None:
    make_account(db, "a@example.com")
    wrong = client.post("/api/auth/login", data={"username": "a@example.com", "password": "wrong-password"})
    unknown = client.post("/api/auth/login", data={"username": "nobody@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


def test_inactive_user_cannot_log_in(client: TestClient, db: Session) -> None:
    user = make_account(db, "a@example.com")
    user.is_active = False
    db.commit()
    response = client.post("/api/auth/login", data={"username": "a@example.com", "password": PASSWORD})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_existing_token_stops_working_when_deactivated(client: TestClient, db: Session) -> None:
    user = make_account(db, "a@example.com")
    headers = login_headers(client, "a@example.com")
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    user.is_active = False
    db.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_me_returns_current_user(client: TestClient, db: Session) -> None:
    make_account(db, "a@example.com")
    response = client.get("/api/auth/me", headers=login_headers(client, "a@example.com"))
    assert response.status_code == 200
    assert response.json()["email"] == "a@example.com"
    assert "password_hash" not in response.json()


def test_me_without_token_gives_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_expired_token_gives_401(client: TestClient, db: Session) -> None:
    user = make_account(db, "a@example.com")
    token = create_access_token(user.id, Role.STUDENT, expires_delta=timedelta(seconds=-10))
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_with_garbage_token_gives_401(client: TestClient) -> None:
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_role_in_token_is_not_trusted(client: TestClient, db: Session) -> None:
    """A token claiming 'admin' still gets the role stored in the database."""
    user = make_account(db, "a@example.com", Role.STUDENT)
    token = create_access_token(user.id, Role.ADMIN)
    response = client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert db.get(User, user.id).role == Role.STUDENT  # type: ignore[union-attr]
