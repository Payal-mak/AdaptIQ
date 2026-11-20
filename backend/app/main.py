from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, health, users
from app.core.config import get_settings, validate_jwt_secret


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Runs once at startup: refuse to start with a weak JWT secret."""
    validate_jwt_secret(get_settings().jwt_secret)
    yield


app = FastAPI(title="AdaptIQ", lifespan=lifespan)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
