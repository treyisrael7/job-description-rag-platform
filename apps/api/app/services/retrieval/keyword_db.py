"""PostgreSQL full-text search over document chunks."""

import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentChunk, InterviewSource
from app.services.retrieval.constants import Scope
from app.services.retrieval.keyword_query import _normalize_keyword_query_text
from app.services.retrieval.payloads import _chunk_payload_from_row, _expanded_section_types


async def retrieve_chunks_keyword(
    db: AsyncSession,
    document_id: uuid.UUID,
    query_text: str,
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
    Search document_chunks by PostgreSQL full-text search ranking.

    This is the keyword retrieval path that complements vector search:
    - converts the raw query text into a PostgreSQL tsquery
    - filters the same chunk corpus as semantic retrieval
    - ranks matches with ts_rank_cd(search_vector, tsquery)

    Returns the same chunk payload shape as retrieve_chunks() so callers can
    later merge keyword and semantic candidates without extra mapping.
    """
    normalized_query = _normalize_keyword_query_text(query_text)
    if not normalized_query:
        return []

    expanded_section_types = _expanded_section_types(section_types)
    extra_doc_ids = additional_document_ids or []

    limit = _sql_limit_override if _sql_limit_override is not None else top_k

    # websearch_to_tsquery is more forgiving for natural user input than
    # plainto_tsquery, and the preprocessor above keeps JD/technical tokens
    # readable while expanding a few high-value keyword variants.
    tsquery = func.websearch_to_tsquery("english", normalized_query)
    rank_col = func.ts_rank_cd(DocumentChunk.search_vector, tsquery).label("score")

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
            rank_col,
        )
        .join(InterviewSource, DocumentChunk.source_id == InterviewSource.id)
        .where(DocumentChunk.search_vector.op("@@")(tsquery))
        .order_by(rank_col.desc(), DocumentChunk.page_number.asc(), DocumentChunk.chunk_index.asc())
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
