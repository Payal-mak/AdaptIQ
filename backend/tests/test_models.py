import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Evaluation,
    FeedbackReport,
    InterviewSession,
    InterviewTurn,
    Question,
    Topic,
    User,
)
from app.models.enums import Level, QuestionStatus, Role


def make_user(db: Session, email: str = "a@example.com", role: Role = Role.STUDENT) -> User:
    user = User(email=email, full_name="Test User", password_hash="x", role=role)
    db.add(user)
    db.flush()
    return user


def make_topic(db: Session, name: str = "DBMS") -> Topic:
    topic = Topic(name=name)
    db.add(topic)
    db.flush()
    return topic


def make_turn(db: Session) -> InterviewTurn:
    student = make_user(db)
    topic = make_topic(db)
    session = InterviewSession(student_id=student.id, topic_id=topic.id)
    db.add(session)
    db.flush()
    turn = InterviewTurn(session_id=session.id, turn_number=1, question_text="What is a key?", level=Level.MEDIUM)
    db.add(turn)
    db.flush()
    return turn


def test_user_defaults(db: Session) -> None:
    user = make_user(db)
    assert user.role == Role.STUDENT
    assert user.is_active is True
    assert user.created_at is not None


def test_duplicate_email_rejected(db: Session) -> None:
    make_user(db, "dup@example.com")
    with pytest.raises(IntegrityError):
        make_user(db, "dup@example.com")


def test_question_defaults_to_pending(db: Session) -> None:
    topic = make_topic(db)
    q = Question(topic_id=topic.id, level=Level.EASY, text="What is SQL?", expected_points=["query language"])
    db.add(q)
    db.flush()
    assert q.status == QuestionStatus.PENDING
    assert q.expected_points == ["query language"]
    assert q.topic.name == "DBMS"


def test_invalid_level_rejected_by_database(db: Session) -> None:
    topic = make_topic(db)
    with pytest.raises(IntegrityError):
        db.execute(
            text("INSERT INTO questions (topic_id, level, text, expected_points, status, source) "
                 "VALUES (:t, 'impossible', 'q', '[]', 'pending', 'ai')"),
            {"t": topic.id},
        )


def test_session_starts_in_progress_at_medium(db: Session) -> None:
    turn = make_turn(db)
    session = turn.session
    assert session.status.value == "in_progress"
    assert session.current_level == Level.MEDIUM
    assert [t.turn_number for t in session.turns] == [1]


def test_turn_numbers_unique_per_session(db: Session) -> None:
    turn = make_turn(db)
    db.add(InterviewTurn(session_id=turn.session_id, turn_number=1, question_text="dup", level=Level.EASY))
    with pytest.raises(IntegrityError):
        db.flush()


def test_evaluation_score_must_be_0_to_10(db: Session) -> None:
    turn = make_turn(db)
    db.add(Evaluation(turn_id=turn.id, score=11, confidence=0.9))
    with pytest.raises(IntegrityError):
        db.flush()


def test_evaluation_valid_and_override(db: Session) -> None:
    turn = make_turn(db)
    faculty = make_user(db, "f@example.com", Role.FACULTY)
    ev = Evaluation(turn_id=turn.id, score=6.5, confidence=0.4, needs_review=True)
    db.add(ev)
    db.flush()
    assert ev.override_score is None
    ev.override_score = 8
    ev.override_by = faculty.id
    db.flush()
    assert ev.override_score == 8


def test_one_evaluation_per_turn(db: Session) -> None:
    turn = make_turn(db)
    db.add(Evaluation(turn_id=turn.id, score=5, confidence=0.9))
    db.flush()
    db.add(Evaluation(turn_id=turn.id, score=6, confidence=0.9))
    with pytest.raises(IntegrityError):
        db.flush()


def test_one_feedback_report_per_session(db: Session) -> None:
    turn = make_turn(db)
    db.add(FeedbackReport(session_id=turn.session_id, proficiency_level=Level.MEDIUM))
    db.flush()
    db.add(FeedbackReport(session_id=turn.session_id, proficiency_level=Level.HARD))
    with pytest.raises(IntegrityError):
        db.flush()
