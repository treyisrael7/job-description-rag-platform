"""Interview source: JD, resume, company info, notes - attached to a document (Interview Kit)."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SourceType(str, Enum):
    JD = "jd"
    RESUME = "resume"
    COMPANY = "company"
    NOTES = "notes"


class InterviewSource(Base):
    """A source attached to a document (Interview Kit). Each source has chunks/embeddings."""

    __tablename__ = "interview_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(nullable=False)  # "jd" | "resume" | "company" | "notes"
    title: Mapped[str] = mapped_column(nullable=False)
    original_file_name: Mapped[str | None] = mapped_column(nullable=True)
    url: Mapped[str | None] = mapped_column(nullable=True)
    profile_json: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (Index("ix_interview_sources_document_id", "document_id"),)
