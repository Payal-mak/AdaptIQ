from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Level, SessionStatus, enum_type


class InterviewSession(Base):
    """One mock interview: one student, one topic."""

    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    status: Mapped[SessionStatus] = mapped_column(enum_type(SessionStatus, "ck_sessions_status"), default=SessionStatus.IN_PROGRESS)
    current_level: Mapped[Level] = mapped_column(enum_type(Level, "ck_sessions_current_level"), default=Level.MEDIUM)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Filled when the interview ends (Step 11): proficiency level and average score.
    final_level: Mapped[Level | None] = mapped_column(enum_type(Level, "ck_sessions_final_level"))
    overall_score: Mapped[float | None] = mapped_column(Float)

    turns: Mapped[list["InterviewTurn"]] = relationship(
        back_populates="session", order_by="InterviewTurn.turn_number"
    )


class InterviewTurn(Base):
    """One question asked in a session, and the student's answer to it."""

    __tablename__ = "interview_turns"
    __table_args__ = (UniqueConstraint("session_id", "turn_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), index=True)
    turn_number: Mapped[int] = mapped_column(Integer)
    # Null for follow-up questions, which are generated and not in the bank.
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"))
    # Copy of the question as asked, so later edits to the bank don't change history.
    question_text: Mapped[str] = mapped_column(Text)
    level: Mapped[Level] = mapped_column(enum_type(Level, "ck_turns_level"))
    is_follow_up: Mapped[bool] = mapped_column(default=False)
    parent_turn_id: Mapped[int | None] = mapped_column(ForeignKey("interview_turns.id"))
    answer_text: Mapped[str | None] = mapped_column(Text)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[InterviewSession] = relationship(back_populates="turns")
