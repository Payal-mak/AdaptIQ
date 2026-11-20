"""Shared fixtures. Model tests use a separate `adaptiq_test` database (needs Docker running)."""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (registers all models)
from app.core.config import get_settings
from app.db.base import Base

TEST_DB_NAME = "adaptiq_test"


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
