"""Add interview_sources table and source_id to document_chunks.

Interview Kit: multiple sources (JD, resume, company, notes) per document.
Migrates existing documents: creates one source (type=jd) per document with chunks,
attaches chunks to that source.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20250304000000"
down_revision: Union[str, None] = "20250303300000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create interview_sources table
    op.create_table(
        "interview_sources",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("original_file_name", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_sources_document_id",
        "interview_sources",
        ["document_id"],
    )

    # 2. Add source_id to document_chunks (nullable for migration)
    op.add_column(
        "document_chunks",
        sa.Column("source_id", sa.Uuid(), nullable=True),
    )

    # 3. Backfill: for each document with chunks, create a source and attach chunks
    conn = op.get_bind()
    result = conn.execute(
        sa.text("""
            SELECT DISTINCT d.id, d.filename
            FROM documents d
            INNER JOIN document_chunks dc ON dc.document_id = d.id
        """)
    )
    rows = result.fetchall()

    for doc_id, filename in rows:
        # Create source for this document
        ins = sa.text("""
            INSERT INTO interview_sources (id, document_id, source_type, title, original_file_name, created_at)
            VALUES (gen_random_uuid(), :doc_id, 'jd', :title, :original_file_name, now())
            RETURNING id
        """)
        r = conn.execute(
            ins,
            {"doc_id": doc_id, "title": filename or "Job Description", "original_file_name": filename},
        )
        source_row = r.fetchone()
        if source_row:
            source_id = source_row[0]
            conn.execute(
                sa.text("UPDATE document_chunks SET source_id = :sid WHERE document_id = :did"),
                {"sid": source_id, "did": doc_id},
            )

    # 4. Make source_id NOT NULL
    op.alter_column(
        "document_chunks",
        "source_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )

    # 5. Add FK constraint
    op.create_foreign_key(
        "fk_document_chunks_source_id",
        "document_chunks",
        "interview_sources",
        ["source_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 6. Drop old unique constraint, add new one
    op.drop_constraint(
        "uq_document_chunks_document_id_chunk_index",
        "document_chunks",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_document_chunks_source_id_chunk_index",
        "document_chunks",
        ["source_id", "chunk_index"],
    )

    # 7. Add index for source_id lookups
    op.create_index(
        "ix_document_chunks_source_id",
        "document_chunks",
        ["source_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_source_id", table_name="document_chunks")
    op.drop_constraint(
        "uq_document_chunks_source_id_chunk_index",
        "document_chunks",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_document_chunks_document_id_chunk_index",
        "document_chunks",
        ["document_id", "chunk_index"],
    )
    op.drop_constraint("fk_document_chunks_source_id", "document_chunks", type_="foreignkey")
    op.drop_column("document_chunks", "source_id")
    op.drop_index("ix_interview_sources_document_id", table_name="interview_sources")
    op.drop_table("interview_sources")
