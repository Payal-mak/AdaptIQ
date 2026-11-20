"""schema fixes: Proficiency enum, composite index, ON DELETE CASCADE, JSONB

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column, constraint name) for the two columns that switch from Level to Proficiency.
PROFICIENCY_COLUMNS = [
    ("feedback_reports", "proficiency_level", "ck_feedback_proficiency"),
    ("interview_sessions", "final_level", "ck_sessions_final_level"),
]
LEVEL_TO_PROFICIENCY = {"easy": "beginner", "medium": "intermediate", "hard": "advanced"}

# (table, column, referenced table, existing FK name)
CASCADE_FKS = [
    ("interview_turns", "session_id", "interview_sessions", "interview_turns_session_id_fkey"),
    ("evaluations", "turn_id", "interview_turns", "evaluations_turn_id_fkey"),
    ("feedback_reports", "session_id", "interview_sessions", "feedback_reports_session_id_fkey"),
]


def _swap_check(table: str, column: str, name: str, old: dict[str, str], new_values: list[str]) -> None:
    """Drop the old CHECK, rewrite existing values, add the new CHECK."""
    op.drop_constraint(name, table, type_="check")
    for old_value, new_value in old.items():
        op.execute(sa.text(f"UPDATE {table} SET {column} = '{new_value}' WHERE {column} = '{old_value}'"))
    allowed = ", ".join(f"'{v}'" for v in new_values)
    op.create_check_constraint(name, table, f"{column} IN ({allowed})")


def upgrade() -> None:
    # 1. Proficiency enum for the final result columns.
    for table, column, name in PROFICIENCY_COLUMNS:
        _swap_check(table, column, name, LEVEL_TO_PROFICIENCY, ["beginner", "intermediate", "advanced"])

    # 2. Composite index for the question-picking query.
    op.create_index("ix_questions_topic_level_status", "questions", ["topic_id", "level", "status"])

    # 3. ON DELETE CASCADE on the child foreign keys.
    for table, column, ref_table, fk_name in CASCADE_FKS:
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.create_foreign_key(fk_name, table, ref_table, [column], ["id"], ondelete="CASCADE")

    # 4. JSON -> JSONB.
    op.alter_column(
        "questions",
        "expected_points",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
        postgresql_using="expected_points::jsonb",
    )


def downgrade() -> None:
    op.alter_column(
        "questions",
        "expected_points",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        existing_nullable=False,
        postgresql_using="expected_points::json",
    )

    for table, column, ref_table, fk_name in CASCADE_FKS:
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.create_foreign_key(fk_name, table, ref_table, [column], ["id"])

    op.drop_index("ix_questions_topic_level_status", table_name="questions")

    reverse = {v: k for k, v in LEVEL_TO_PROFICIENCY.items()}
    for table, column, name in PROFICIENCY_COLUMNS:
        _swap_check(table, column, name, reverse, ["easy", "medium", "hard"])
