"""Retrieval helpers for resume-to-JD gap analysis."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InterviewSource
from app.services.interview import get_user_resume_document_id
from app.services.retrieval import embed_query, retrieve_chunks


async def resolve_resume_sources(
    db: AsyncSession,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """Resolve attached and account-level resume sources for a JD document."""
    additional_document_ids: list[uuid.UUID] = []

    account_resume_document_id = await get_user_resume_document_id(db, user_id)
    if account_resume_document_id and account_resume_document_id != document_id:
        additional_document_ids.append(account_resume_document_id)

    source_result = await db.execute(
        select(InterviewSource)
        .where(
            InterviewSource.document_id.in_([document_id] + additional_document_ids),
            InterviewSource.source_type == "resume",
        )
        .order_by(InterviewSource.created_at.asc())
    )
    sources = source_result.scalars().all()

    return {
        "sources": sources,
        "additional_document_ids": additional_document_ids,
        "account_resume_document_id": account_resume_document_id,
    }


async def _retrieve_gap_evidence(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    query_text: str,
    source_types: list[str],
    top_k: int,
    doc_domain: str | None = None,
    additional_document_ids: list[uuid.UUID] | None = None,
) -> list[dict]:
    query_embedding = embed_query(query_text)
    chunks = await retrieve_chunks(
        db=db,
        document_id=document_id,
        query_embedding=query_embedding,
        query_text=query_text,
        top_k=top_k,
        include_low_signal=False,
        section_types=None,
        doc_domain=doc_domain,
        source_types=source_types,
        additional_document_ids=additional_document_ids,
    )
    return [
        {
            "chunkId": str(c["chunkId"]),
            "page": c.get("page"),
            "snippet": c.get("text") or c.get("snippet", ""),
            "sourceTitle": c.get("sourceTitle", ""),
            "sourceType": c.get("sourceType", ""),
            "retrieval_source": c.get("retrieval_source"),
            "semantic_score": c.get("semantic_score"),
            "keyword_score": c.get("keyword_score"),
            "final_score": c.get("final_score"),
        }
        for c in chunks
    ]


async def retrieve_jd_evidence_for_target(
    db: AsyncSession,
    document_id: uuid.UUID,
    query_text: str,
    top_k: int = 3,
) -> list[dict]:
    """Retrieve JD-side evidence for a requirement target."""
    return await _retrieve_gap_evidence(
        db,
        document_id=document_id,
        query_text=query_text,
        source_types=["jd"],
        top_k=top_k,
        doc_domain="job_description",
    )


async def retrieve_resume_evidence_for_target(
    db: AsyncSession,
    document_id: uuid.UUID,
    query_text: str,
    additional_document_ids: list[uuid.UUID] | None = None,
    top_k: int = 4,
) -> list[dict]:
    """Retrieve raw resume evidence across attached and account-level resume sources."""
    return await _retrieve_gap_evidence(
        db,
        document_id=document_id,
        query_text=query_text,
        source_types=["resume"],
        top_k=top_k,
        doc_domain=None,
        additional_document_ids=additional_document_ids,
    )
