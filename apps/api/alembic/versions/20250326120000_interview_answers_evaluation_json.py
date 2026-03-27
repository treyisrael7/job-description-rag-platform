"""Add interview_answers.evaluation_json for structured evaluation snapshot."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20250326120000"
down_revision = "20250324120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_answers",
        sa.Column("evaluation_json", JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        """
        UPDATE interview_answers
        SET evaluation_json = jsonb_build_object(
            'score', COALESCE(
                feedback_json->'llm_score_0_10',
                feedback_json->'score',
                '0'::jsonb
            ),
            'strengths', COALESCE(feedback_json->'strengths', '[]'::jsonb),
            'gaps', COALESCE(feedback_json->'gaps', '[]'::jsonb),
            'citations', COALESCE(feedback_json->'citations', '[]'::jsonb)
        )
        WHERE feedback_json IS NOT NULL
        """
    )
    op.execute(
        "UPDATE interview_answers SET evaluation_json = '{}'::jsonb WHERE evaluation_json IS NULL"
    )
    op.alter_column(
        "interview_answers",
        "evaluation_json",
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def downgrade() -> None:
    op.drop_column("interview_answers", "evaluation_json")
