import enum

from sqlalchemy import Enum as SAEnum


class Role(str, enum.Enum):
    STUDENT = "student"
    FACULTY = "faculty"
    ADMIN = "admin"


class Level(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Proficiency(str, enum.Enum):
    """The student's final result for a topic (different from question Level)."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class QuestionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class QuestionSource(str, enum.Enum):
    AI = "ai"
    MANUAL = "manual"


class SessionStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


def enum_type(cls: type[enum.Enum], name: str, length: int = 20) -> SAEnum:
    """Store an Enum as a plain string column holding the enum's value (easy to migrate).

    `name` becomes the CHECK constraint name, so it must be unique per column.
    """
    return SAEnum(cls, native_enum=False, create_constraint=True, name=name, length=length, values_callable=lambda e: [m.value for m in e])
