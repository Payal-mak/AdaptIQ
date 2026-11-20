from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    database: str


@router.get("/health", response_model=HealthResponse)
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    """Report app status and whether the database answers a trivial query."""
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # report any DB failure instead of crashing
        database = f"error: {type(exc).__name__}"
    return HealthResponse(status="ok", database=database)
