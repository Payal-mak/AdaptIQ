from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Level, QuestionSource, QuestionStatus, enum_type
from app.models.topic import Topic


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    level: Mapped[Level] = mapped_column(enum_type(Level, "ck_questions_level"))
    text: Mapped[str] = mapped_column(Text)
    # Key points a good answer should cover; used by the Evaluator Agent.
    expected_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[QuestionStatus] = mapped_column(enum_type(QuestionStatus, "ck_questions_status"), default=QuestionStatus.PENDING)
    source: Mapped[QuestionSource] = mapped_column(enum_type(QuestionSource, "ck_questions_source"), default=QuestionSource.AI)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    topic: Mapped[Topic] = relationship()
