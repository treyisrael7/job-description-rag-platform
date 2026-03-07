"""Add documents.competencies JSONB for Competency Map extraction."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20250305000000"
down_revision: Union[str, None] = "20250304000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("competencies", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "competencies")
