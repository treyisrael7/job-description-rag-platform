"""Add documents.rubric_json JSONB for JD evaluation dimensions."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20250326130000"
down_revision: Union[str, None] = "20250326120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("rubric_json", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "rubric_json")
