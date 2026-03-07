"""Add interview_sessions.role_profile_json JSONB for Role Intelligence."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20250303210000"
down_revision: Union[str, None] = "20250303200000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column("role_profile_json", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "role_profile_json")
