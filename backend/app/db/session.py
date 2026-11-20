from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create the engine lazily so importing the app never needs a live DB."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: give a request its own DB session, close it after."""
    session_factory = sessionmaker(bind=get_engine(), autoflush=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
