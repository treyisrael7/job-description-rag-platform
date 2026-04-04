"""Add interview_retrieval_feedback for RAG quality signals."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260404120000"
down_revision: Union[str, None] = "20250328140000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_retrieval_feedback",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_chunk_ids", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["answer_id"], ["interview_answers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["interview_questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("answer_id", name="uq_interview_retrieval_feedback_answer_id"),
    )
    op.create_index(
        "ix_interview_retrieval_feedback_user_id",
        "interview_retrieval_feedback",
        ["user_id"],
    )
    op.create_index(
        "ix_interview_retrieval_feedback_document_id",
        "interview_retrieval_feedback",
        ["document_id"],
    )
    op.create_index(
        "ix_interview_retrieval_feedback_created_at",
        "interview_retrieval_feedback",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_interview_retrieval_feedback_created_at", table_name="interview_retrieval_feedback")
    op.drop_index("ix_interview_retrieval_feedback_document_id", table_name="interview_retrieval_feedback")
    op.drop_index("ix_interview_retrieval_feedback_user_id", table_name="interview_retrieval_feedback")
    op.drop_table("interview_retrieval_feedback")
