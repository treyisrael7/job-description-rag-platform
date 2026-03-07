"""Retrieval: embed query, search document_chunks, MMR diversification."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models import DocumentChunk, InterviewSource

# Backward compat: expand canonical section types to legacy job description section names in DB
SECTION_TYPE_EXPANSION: dict[str, list[str]] = {
    "tools": ["tools", "tools_technologies"],
    "qualifications": ["qualifications", "preferred_qualifications"],
    "about": ["about", "position_summary", "company_info"],
    "other": ["other", "location", "company_info"],
}
from app.services.ingestion import _create_embeddings

# Query keywords -> suggested section types (canonical: responsibilities, qualifications, tools, compensation, about, other)
QUERY_SECTION_HINTS: dict[str, list[str]] = {
    "skill": ["qualifications", "tools"],
    "qualification": ["qualifications"],
    "responsibilit": ["responsibilities"],
    "requirement": ["qualifications"],
    "salary": ["compensation"],
    "salaries": ["compensation"],
    "pay": ["compensation"],
    "compensation": ["compensation"],
    "benefits": ["compensation"],
    "wage": ["compensation"],
    "how much": ["compensation"],
    "location": ["about", "other"],
    "remote": ["about", "other"],
    "company": ["about", "other"],
    "role": ["about"],
    "job": ["about"],
    "tool": ["tools"],
    "tech": ["tools"],
}


def suggest_section_filters(query: str) -> list[str] | None:
    """If query suggests specific sections, return section_types to filter."""
    q = query.lower().strip()
    words = set(re.findall(r"\b\w+\b", q))
    suggested: set[str] = set()
    for hint, sections in QUERY_SECTION_HINTS.items():
        if hint in q or any(hint in w for w in words):
            suggested.update(sections)
    return list(suggested) if suggested else None


def embed_query(query: str) -> list[float]:
    """Embed a single query string. Returns embedding vector."""
    embeddings = _create_embeddings([query])
    return embeddings[0]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity (dot product for normalized vectors)."""
    return sum(x * y for x, y in zip(a, b))


def _mmr_select(
    candidates: list[dict],
    query_embedding: list[float],
    top_k: int,
    lambda_: float,
) -> list[dict]:
    """
    Maximal Marginal Relevance: select diverse top_k from candidates.
    candidates have: id, page_number, content, embedding, score (sim to query).
    """
    if len(candidates) <= top_k:
        for c in candidates[:top_k]:
            c.pop("embedding", None)
        return candidates[:top_k]

    selected: list[dict] = []
    remaining = list(candidates)

    while len(selected) < top_k and remaining:
        best_idx = -1
        best_mmr = float("-inf")
        for i, c in enumerate(remaining):
            sim_q = c["score"]
            max_sim_sel = 0.0
            if selected:
                for s in selected:
                    sim_d = _cosine_sim(c["embedding"], s["embedding"])
                    max_sim_sel = max(max_sim_sel, sim_d)
            mmr = lambda_ * sim_q - (1 - lambda_) * max_sim_sel
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i
        if best_idx < 0:
            break
        chosen = remaining.pop(best_idx)
        selected.append(chosen)

    for c in selected:
        c.pop("embedding", None)
    return selected


async def retrieve_chunks(
    db: AsyncSession,
    document_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    include_low_signal: bool = False,
    section_types: list[str] | None = None,
    doc_domain: str | None = None,
    source_types: list[str] | None = None,
    additional_document_ids: list[uuid.UUID] | None = None,
) -> list[dict]:
    """
    Search document_chunks by cosine similarity.
    Joins with interview_sources for metadata. Fetches top candidates, filters, applies MMR.
    By default excludes is_low_signal chunks; pass include_low_signal=true for contact queries.
    When source_types is None, returns chunks from all sources (existing behavior).
    Returns list of {
        chunk_id, chunkId, page_number, page, snippet, text, score,
        sourceType, sourceTitle, is_low_signal, section_type
    }.
    """
    distance_col = DocumentChunk.embedding.cosine_distance(query_embedding)
    score_col = (1 - distance_col).label("score")
    limit = max(top_k, settings.top_n_candidates)

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.page_number,
            DocumentChunk.content,
            DocumentChunk.embedding,
            DocumentChunk.is_low_signal,
            DocumentChunk.section_type,
            InterviewSource.source_type.label("src_type"),
            InterviewSource.title.label("src_title"),
            score_col,
        )
        .join(InterviewSource, DocumentChunk.source_id == InterviewSource.id)
        .where(
            DocumentChunk.document_id.in_([document_id] + (additional_document_ids or []))
        )
        .where(DocumentChunk.embedding.isnot(None))
        .order_by(distance_col.asc())
        .limit(limit)
    )
    if not include_low_signal:
        stmt = stmt.where(DocumentChunk.is_low_signal == False)
    if section_types:
        expanded: set[str] = set()
        for st in section_types:
            expanded.add(st)
            expanded.update(SECTION_TYPE_EXPANSION.get(st, []))
        stmt = stmt.where(DocumentChunk.section_type.in_(list(expanded)))
    if doc_domain:
        stmt = stmt.where(DocumentChunk.doc_domain == doc_domain)
    if source_types:
        stmt = stmt.where(InterviewSource.source_type.in_(source_types))

    result = await db.execute(stmt)
    rows = result.all()

    candidates = []
    for row in rows:
        source_type_val = getattr(row, "src_type", None) or "jd"
        source_title_val = getattr(row, "src_title", None) or ""
        candidates.append({
            "chunk_id": str(row.id),
            "chunkId": str(row.id),
            "page_number": row.page_number,
            "page": row.page_number,
            "snippet": row.content,
            "text": row.content,
            "score": round(float(row.score), 6),
            "is_low_signal": bool(row.is_low_signal),
            "section_type": getattr(row, "section_type", None),
            "sourceType": source_type_val,
            "sourceTitle": source_title_val,
            "embedding": row.embedding,
        })

    diversified = _mmr_select(
        candidates,
        query_embedding,
        top_k,
        settings.mmr_lambda,
    )

    return [
        {
            "chunk_id": c["chunk_id"],
            "chunkId": c["chunkId"],
            "page_number": c["page_number"],
            "page": c["page"],
            "snippet": c["snippet"],
            "text": c["text"],
            "score": c["score"],
            "sourceType": c["sourceType"],
            "sourceTitle": c["sourceTitle"],
            "is_low_signal": c.get("is_low_signal", False),
            "section_type": c.get("section_type"),
        }
        for c in diversified
    ]
