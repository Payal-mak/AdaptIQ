import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import Role
from app.scripts.create_admin import create_admin
from app.services import user_service
from tests.conftest import PASSWORD, login_headers, make_account


def test_student_gets_403_on_admin_endpoints(client: TestClient, db: Session) -> None:
    student = make_account(db, "s@example.com")
    headers = login_headers(client, "s@example.com")
    new_user = {"email": "x@example.com", "full_name": "X", "password": PASSWORD}
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.post("/api/users", headers=headers, json=new_user).status_code == 403
    assert client.patch(f"/api/users/{student.id}", headers=headers, json={"role": "admin"}).status_code == 403


def test_admin_endpoints_without_token_give_401(client: TestClient) -> None:
    assert client.get("/api/users").status_code == 401


def test_admin_can_create_faculty(client: TestClient, db: Session) -> None:
    make_account(db, "admin@example.com", Role.ADMIN)
    headers = login_headers(client, "admin@example.com")
    response = client.post(
        "/api/users",
        headers=headers,
        json={"email": "Prof@Example.com", "full_name": "Prof", "password": PASSWORD, "role": "faculty"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "faculty"
    assert response.json()["email"] == "prof@example.com"
    assert "password_hash" not in response.json()
    login_headers(client, "prof@example.com")  # the new faculty member can log in


def test_admin_create_duplicate_gives_409(client: TestClient, db: Session) -> None:
    make_account(db, "admin@example.com", Role.ADMIN)
    headers = login_headers(client, "admin@example.com")
    body = {"email": "admin@example.com", "full_name": "Dup", "password": PASSWORD, "role": "faculty"}
    assert client.post("/api/users", headers=headers, json=body).status_code == 409


def test_admin_can_list_and_filter_by_role(client: TestClient, db: Session) -> None:
    make_account(db, "admin@example.com", Role.ADMIN)
    make_account(db, "f@example.com", Role.FACULTY)
    make_account(db, "s@example.com", Role.STUDENT)
    headers = login_headers(client, "admin@example.com")
    assert len(client.get("/api/users", headers=headers).json()) == 3
    faculty = client.get("/api/users", headers=headers, params={"role": "faculty"}).json()
    assert [u["email"] for u in faculty] == ["f@example.com"]


def test_admin_can_change_role_and_deactivate_others(client: TestClient, db: Session) -> None:
    make_account(db, "admin@example.com", Role.ADMIN)
    student = make_account(db, "s@example.com")
    headers = login_headers(client, "admin@example.com")
    promoted = client.patch(f"/api/users/{student.id}", headers=headers, json={"role": "faculty"})
    assert promoted.status_code == 200 and promoted.json()["role"] == "faculty"
    disabled = client.patch(f"/api/users/{student.id}", headers=headers, json={"is_active": False})
    assert disabled.status_code == 200 and disabled.json()["is_active"] is False


def test_admin_cannot_deactivate_self(client: TestClient, db: Session) -> None:
    admin = make_account(db, "admin@example.com", Role.ADMIN)
    headers = login_headers(client, "admin@example.com")
    response = client.patch(f"/api/users/{admin.id}", headers=headers, json={"is_active": False})
    assert response.status_code == 400
    assert client.get("/api/auth/me", headers=headers).status_code == 200


def test_admin_cannot_remove_own_admin_role(client: TestClient, db: Session) -> None:
    admin = make_account(db, "admin@example.com", Role.ADMIN)
    headers = login_headers(client, "admin@example.com")
    response = client.patch(f"/api/users/{admin.id}", headers=headers, json={"role": "student"})
    assert response.status_code == 400


def test_patch_unknown_user_gives_404(client: TestClient, db: Session) -> None:
    make_account(db, "admin@example.com", Role.ADMIN)
    headers = login_headers(client, "admin@example.com")
    assert client.patch("/api/users/99999", headers=headers, json={"is_active": False}).status_code == 404


def test_demoted_admin_loses_access_immediately(client: TestClient, db: Session) -> None:
    make_account(db, "root@example.com", Role.ADMIN)
    other = make_account(db, "other@example.com", Role.ADMIN)
    other_headers = login_headers(client, "other@example.com")
    root_headers = login_headers(client, "root@example.com")
    assert client.get("/api/users", headers=other_headers).status_code == 200
    client.patch(f"/api/users/{other.id}", headers=root_headers, json={"role": "student"})
    assert client.get("/api/users", headers=other_headers).status_code == 403


def test_create_admin_script_function(db: Session) -> None:
    create_admin(db, " Boss@Example.com ", "The Boss", PASSWORD)
    boss = user_service.get_by_email(db, "boss@example.com")
    assert boss is not None
    assert boss.role == Role.ADMIN
    assert boss.password_hash != PASSWORD


def test_create_admin_refuses_existing_email(db: Session) -> None:
    make_account(db, "boss@example.com", Role.STUDENT)
    with pytest.raises(user_service.EmailAlreadyExistsError):
        create_admin(db, "boss@example.com", "Boss", PASSWORD)
    existing = user_service.get_by_email(db, "boss@example.com")
    assert existing is not None and existing.role == Role.STUDENT
