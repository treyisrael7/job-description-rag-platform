"""Add interview_sessions.performance_profile JSONB for session-level score aggregates."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20250324120000"
down_revision = "20250309000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column("performance_profile", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "performance_profile")
