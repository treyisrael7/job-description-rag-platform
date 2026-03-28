"""Add users.plan and monthly evaluation usage counters."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20250326140000"
down_revision: Union[str, None] = "20250326130000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("plan", sa.String(length=32), server_default="free", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("evaluations_this_month", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("evaluation_usage_month", sa.String(length=7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "evaluation_usage_month")
    op.drop_column("users", "evaluations_this_month")
    op.drop_column("users", "plan")
