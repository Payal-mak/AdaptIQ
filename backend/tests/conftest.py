"""Shared fixtures. DB tests use a separate `adaptiq_test` database (needs Docker running)."""

import os
from collections.abc import Generator

# Tests must not depend on the developer's real .env: set safe values BEFORE the app is imported.
os.environ["JWT_SECRET"] = "test-secret-key-that-is-long-enough-0123456789"
os.environ["ALLOWED_EMAIL_DOMAIN"] = ""
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "120"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import models  # noqa: E402,F401  (registers all models)
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import Role  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import user_service  # noqa: E402

TEST_DB_NAME = "adaptiq_test"
PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session")
def test_engine():  # type: ignore[no-untyped-def]
    """Create adaptiq_test if missing, build all tables in it, drop them at the end."""
    main_url = make_url(get_settings().database_url)
    admin_engine = create_engine(main_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB_NAME}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    except Exception as exc:
        pytest.skip(f"Postgres not reachable (is Docker running?): {type(exc).__name__}")
    finally:
        admin_engine.dispose()

    engine = create_engine(main_url.set(database=TEST_DB_NAME))
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(test_engine) -> Generator[Session, None, None]:  # type: ignore[no-untyped-def]
    """A session whose changes are rolled back after each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """TestClient whose requests use the rolled-back test session."""

    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_account(db: Session, email: str, role: Role = Role.STUDENT, password: str = PASSWORD) -> User:
    """Create a user directly in the test DB."""
    return user_service.create_user(db, email, "Test Person", password, role)


def login_headers(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    """Log in through the real endpoint and return the Authorization header."""
    response = client.post("/api/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ---------------------------------------------------------------- LLM logging fixtures


@pytest.fixture(autouse=True)
def block_main_database_for_llm_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Safety net: if any test lets LLMClient fall back to the default (real) session factory,
    fail loudly instead of writing llm_calls rows into the main database."""

    def blocked() -> None:
        raise RuntimeError("Tests must inject a session factory bound to adaptiq_test, not the real DB")

    monkeypatch.setattr("app.llm.client.default_session_factory", blocked)
    monkeypatch.setattr("app.llm.call_log.default_session_factory", blocked)


@pytest.fixture
def llm_log_factory(test_engine) -> Generator[sessionmaker[Session], None, None]:  # type: ignore[no-untyped-def]
    """Session factory for the LLM call log, bound to the adaptiq_test engine ONLY.
    Rows it commits are deleted after each test (only ever in adaptiq_test)."""
    assert test_engine.url.database == TEST_DB_NAME, "refusing to touch a database that is not adaptiq_test"
    yield sessionmaker(bind=test_engine, expire_on_commit=False)
    with test_engine.begin() as conn:
        assert conn.engine.url.database == TEST_DB_NAME
        conn.execute(text("DELETE FROM llm_calls"))
