"""Add documents.doc_domain: 'general' | 'job_description'."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20250302000000"
down_revision: Union[str, None] = "20250228140000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("doc_domain", sa.String(), nullable=True, server_default="general"),
    )


def downgrade() -> None:
    op.drop_column("documents", "doc_domain")
