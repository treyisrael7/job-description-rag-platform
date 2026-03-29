"""Vector similarity candidate retrieval."""

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import DocumentChunk, InterviewSource
from app.services.retrieval.constants import Scope
from app.services.retrieval.payloads import _chunk_payload_from_row, _expanded_section_types


async def _retrieve_semantic_candidates(
    db: AsyncSession,
    document_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    include_low_signal: bool = False,
    section_types: list[str] | None = None,
    doc_domain: str | None = None,
    source_types: list[str] | None = None,
    additional_document_ids: list[uuid.UUID] | None = None,
    *,
    _scope: Scope = "union",
    _sql_limit_override: int | None = None,
) -> list[dict]:
    """
    Fetch semantic candidates before final ranking / MMR.

    ``_scope``:
    - ``union``: legacy single query over primary + additional (same filters as before).
    - ``primary``: only ``document_id`` rows — JD filters apply to the whole result.
    - ``additional``: only ``additional_document_ids`` — resume rows skip JD section/domain
      filters (same idea as the OR branch for extras in union mode).

    ``_sql_limit_override``: when set, caps DB rows (token budget); otherwise
    ``max(top_k, top_n_candidates)`` for union, or ``top_k`` for scoped fetches.
    """
    distance_col = DocumentChunk.embedding.cosine_distance(query_embedding)
    score_col = (1 - distance_col).label("score")
    extra_doc_ids = additional_document_ids or []

    if _scope == "union":
        limit = _sql_limit_override if _sql_limit_override is not None else max(
            top_k, settings.top_n_candidates
        )
    else:
        limit = _sql_limit_override if _sql_limit_override is not None else top_k

    expanded_section_types = _expanded_section_types(section_types)

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.page_number,
            DocumentChunk.content,
            DocumentChunk.embedding,
            DocumentChunk.content_hash,
            DocumentChunk.is_low_signal,
            DocumentChunk.section_type,
            InterviewSource.source_type.label("src_type"),
            InterviewSource.title.label("src_title"),
            score_col,
        )
        .join(InterviewSource, DocumentChunk.source_id == InterviewSource.id)
        .where(DocumentChunk.embedding.isnot(None))
        .order_by(distance_col.asc())
        .limit(limit)
    )

    if _scope == "primary":
        stmt = stmt.where(DocumentChunk.document_id == document_id)
        if expanded_section_types:
            stmt = stmt.where(DocumentChunk.section_type.in_(expanded_section_types))
        if doc_domain:
            stmt = stmt.where(DocumentChunk.doc_domain == doc_domain)
    elif _scope == "additional":
        if not extra_doc_ids:
            return []
        stmt = stmt.where(DocumentChunk.document_id.in_(extra_doc_ids))
    else:
        stmt = stmt.where(
            DocumentChunk.document_id.in_([document_id] + extra_doc_ids)
        )
        if expanded_section_types:
            if extra_doc_ids:
                stmt = stmt.where(
                    or_(
                        and_(
                            DocumentChunk.document_id == document_id,
                            DocumentChunk.section_type.in_(expanded_section_types),
                        ),
                        DocumentChunk.document_id.in_(extra_doc_ids),
                    )
                )
            else:
                stmt = stmt.where(DocumentChunk.section_type.in_(expanded_section_types))
        if doc_domain:
            if extra_doc_ids:
                stmt = stmt.where(
                    or_(
                        and_(
                            DocumentChunk.document_id == document_id,
                            DocumentChunk.doc_domain == doc_domain,
                        ),
                        DocumentChunk.document_id.in_(extra_doc_ids),
                    )
                )
            else:
                stmt = stmt.where(DocumentChunk.doc_domain == doc_domain)

    if not include_low_signal:
        stmt = stmt.where(DocumentChunk.is_low_signal.is_(False))
    if source_types:
        stmt = stmt.where(InterviewSource.source_type.in_(source_types))

    result = await db.execute(stmt)
    rows = result.all()
    return [_chunk_payload_from_row(row) for row in rows]
