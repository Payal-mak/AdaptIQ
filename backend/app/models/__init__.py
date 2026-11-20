"""Importing this package registers every model on Base.metadata (needed by Alembic)."""

from app.models.evaluation import Evaluation
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession, InterviewTurn
from app.models.llm_call import LlmCall
from app.models.question import Question
from app.models.topic import Topic
from app.models.user import User

__all__ = [
    "Evaluation",
    "FeedbackReport",
    "InterviewSession",
    "InterviewTurn",
    "LlmCall",
    "Question",
    "Topic",
    "User",
]
