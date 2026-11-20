from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


class FakeSession:
    """Stands in for a DB session so the test needs no running database."""

    def __init__(self, fail: bool) -> None:
        self.fail = fail

    def execute(self, *args: object, **kwargs: object) -> None:
        if self.fail:
            raise OperationalError("SELECT 1", {}, Exception("db down"))

    def close(self) -> None:
        pass


def _override(fail: bool):  # type: ignore[no-untyped-def]
    def dependency() -> Generator[FakeSession, None, None]:
        yield FakeSession(fail)

    return dependency


def test_health_ok_when_database_works() -> None:
    app.dependency_overrides[get_db] = _override(fail=False)
    try:
        response = TestClient(app).get("/api/health")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_database_error() -> None:
    app.dependency_overrides[get_db] = _override(fail=True)
    try:
        response = TestClient(app).get("/api/health")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"].startswith("error")
