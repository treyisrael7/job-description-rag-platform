"""Add users.clerk_id for Clerk auth."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20250306000000"
down_revision: Union[str, None] = "20250305000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("clerk_id", sa.String(), nullable=True),
    )
    op.create_unique_constraint("uq_users_clerk_id", "users", ["clerk_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_clerk_id", "users", type_="unique")
    op.drop_column("users", "clerk_id")
