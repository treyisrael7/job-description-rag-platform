"""Add interview_sources.profile_json helper cache."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20250308000000"
down_revision: Union[str, None] = "20250307000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interview_sources",
        sa.Column("profile_json", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_sources", "profile_json")
