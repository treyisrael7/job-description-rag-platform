"""Refactor to interview_sessions, update questions schema, add interview_answers."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20250303100000"
down_revision: Union[str, None] = "20250302100000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old interview tables (order: questions first due to FK)
    op.drop_index("ix_interview_questions_generation_id", table_name="interview_questions")
    op.drop_table("interview_questions")
    op.drop_index("ix_interview_generations_user_doc_mode_diff", table_name="interview_generations")
    op.drop_table("interview_generations")

    # Create interview_sessions
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("difficulty", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_sessions_user_id",
        "interview_sessions",
        ["user_id"],
        unique=False,
    )

    # Create interview_questions (new schema)
    op.create_table(
        "interview_questions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("rubric_json", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_questions_session_id",
        "interview_questions",
        ["session_id"],
        unique=False,
    )

    # Create interview_answers
    op.create_table(
        "interview_answers",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("feedback_json", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["interview_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_answers_question_id",
        "interview_answers",
        ["question_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_interview_answers_question_id", table_name="interview_answers")
    op.drop_table("interview_answers")
    op.drop_index("ix_interview_questions_session_id", table_name="interview_questions")
    op.drop_table("interview_questions")
    op.drop_index("ix_interview_sessions_user_id", table_name="interview_sessions")
    op.drop_table("interview_sessions")

    # Restore old tables
    op.create_table(
        "interview_generations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("difficulty", sa.String(), nullable=False),
        sa.Column("num_questions", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_generations_user_doc_mode_diff",
        "interview_generations",
        ["user_id", "document_id", "mode", "difficulty"],
        unique=False,
    )
    op.create_table(
        "interview_questions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("key_topics", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("evidence", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("rubric_bullets", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["interview_generations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_questions_generation_id",
        "interview_questions",
        ["generation_id"],
        unique=False,
    )
