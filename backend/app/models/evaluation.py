from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Evaluation(Base):
    """The Evaluator Agent's result for one turn, plus an optional faculty override."""

    __tablename__ = "evaluations"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 10", name="ck_evaluations_score_range"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_evaluations_confidence_range"),
        CheckConstraint(
            "override_score IS NULL OR (override_score >= 0 AND override_score <= 10)",
            name="ck_evaluations_override_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    turn_id: Mapped[int] = mapped_column(ForeignKey("interview_turns.id"), unique=True)
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    is_complete: Mapped[bool] = mapped_column(default=True)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    # Low-confidence scores are flagged here for faculty review.
    needs_review: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Faculty override (human-in-the-loop). All null until a faculty member overrides.
    override_score: Mapped[float | None] = mapped_column(Float)
    override_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    override_reason: Mapped[str | None] = mapped_column(Text)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
