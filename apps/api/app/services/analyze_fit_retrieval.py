"""Extra retrieval for analyze-fit when resume education signals are missing from the first pass."""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval.embeddings import embed_query
from app.services.retrieval.orchestration import retrieve_chunks_for_mode

logger = logging.getLogger(__name__)

# If none of the *retrieved* resume chunks match this, we pull a few education-focused chunks.
_EDU_SIGNAL = re.compile(
    r"\b("
    r"bachelor|b\.?s\.?c?|b\.?a\.?|master|m\.?s\.?|mba|ph\.?\s*d|doctorate|associate"
    r"|degree|university|college|gpa|cum\s+laude|honors?|dean'?s\s+list|president'?s\s+list"
    r"|education|coursework|minor|major|academic|certification"
    r")\b",
    re.IGNORECASE,
)

_EDUCATION_RETRIEVAL_QUERY = (
    "Education section university college bachelor master MBA PhD degree minor major "
    "coursework GPA academic honors Dean's list President's list certifications"
)


def _doc_id_str(c: dict) -> str:
    return str(c.get("document_id") or c.get("documentId") or "")


def resume_chunks_have_education_signal(chunks: list[dict], resume_id: uuid.UUID) -> bool:
    """True if any retrieved chunk from ``resume_id`` looks education-related."""
    rid = str(resume_id)
    for c in chunks:
        if _doc_id_str(c) != rid:
            continue
        text = (c.get("snippet") or c.get("text") or "")[:8000]
        if _EDU_SIGNAL.search(text):
            return True
    return False


async def augment_analyze_fit_chunks_with_resume_education(
    db: AsyncSession,
    *,
    resume_id: uuid.UUID,
    chunks: list[dict],
    max_extra: int = 3,
) -> list[dict]:
    """
    When hybrid retrieval missed education-heavy resume chunks, fetch a few semantic
    hits from the resume alone using an education-biased query. Dedupes by chunk id.
    """
    if resume_chunks_have_education_signal(chunks, resume_id):
        return chunks
    try:
        emb = embed_query(_EDUCATION_RETRIEVAL_QUERY)
        extra = await retrieve_chunks_for_mode(
            db=db,
            document_id=resume_id,
            query_embedding=emb,
            top_k=max_extra,
            mode="semantic",
            query_text=_EDUCATION_RETRIEVAL_QUERY,
            enforce_production_chunk_budget=False,
        )
    except Exception as exc:
        logger.warning("analyze-fit education augment retrieval failed: %s", exc)
        return chunks

    seen: set[str] = set()
    for c in chunks:
        cid = str(c.get("chunk_id") or c.get("chunkId") or "")
        if cid:
            seen.add(cid)

    merged = list(chunks)
    for c in extra:
        cid = str(c.get("chunk_id") or c.get("chunkId") or "")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        merged.append(c)
    return merged
