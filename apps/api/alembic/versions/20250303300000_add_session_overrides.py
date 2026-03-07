"""Add interview_sessions override columns for Setup Advanced options."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20250303300000"
down_revision: Union[str, None] = "20250303210000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column("domain_override", sa.String(), nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column("seniority_override", sa.String(), nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column("question_mix_override", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "question_mix_override")
    op.drop_column("interview_sessions", "seniority_override")
    op.drop_column("interview_sessions", "domain_override")
