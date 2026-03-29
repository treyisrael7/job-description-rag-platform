"""JD evidence retrieval and session pool caching for interview flows."""

import asyncio
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.llm_cache import session_pool_get, session_pool_set
from app.models import Document
from app.services.interview.constants import (
    COMPETENCY_EVIDENCE_TOP_K,
    DEFAULT_ROLE_PROFILE,
    SESSION_JD_POOL_TOP_K,
    USER_RESUME_DOC_DOMAIN,
    _MODE_CONFIG,
)
from app.services.retrieval import embed_query, retrieve_chunks

logger = logging.getLogger(__name__)

async def get_user_resume_document_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    """Return document_id of user's account-level resume, or None if none."""
    r = await db.execute(
        select(Document.id).where(
            Document.user_id == user_id,
            Document.doc_domain == USER_RESUME_DOC_DOMAIN,
        )
    )
    row = r.scalar_one_or_none()
    return row if row is not None else None


async def retrieve_interview_evidence(
    db: AsyncSession,
    document_id: uuid.UUID,
    role_profile: dict | None = None,
    mode: str | None = None,
    source_types: list[str] | None = None,
) -> list[dict]:
    """
    Retrieve evidence chunks from job description. Uses role_profile.focusAreas when available,
    else falls back to mode-based retrieval for backward compat.
    When source_types is None, retrieves from all sources (default).
    Returns list of {chunk_id, page_number, snippet, sourceType, sourceTitle} for citations.
    """
    if role_profile:
        focus_areas = role_profile.get("focusAreas") or DEFAULT_ROLE_PROFILE["focusAreas"]
        query = " ".join(focus_areas) + " responsibilities qualifications role requirements"
        section_types = ["responsibilities", "qualifications", "tools", "about"]
    elif mode:
        config = _MODE_CONFIG.get(mode)
        if not config:
            raise ValueError(f"Invalid mode: {mode}")
        section_types, query = config
    else:
        section_types = ["responsibilities", "qualifications", "tools", "about"]
        query = "job responsibilities qualifications tools technologies about company role"

    query_embedding = embed_query(query)
    chunks = await retrieve_chunks(
        db=db,
        document_id=document_id,
        query_embedding=query_embedding,
        query_text=query,
        top_k=min(INTERVIEW_EVIDENCE_TOP_K, settings.top_k_max * 2),
        include_low_signal=False,
        section_types=section_types,
        doc_domain="job_description",
        source_types=source_types,
    )

    # Fallback: if no chunks match section filter, retry without section filter
    if not chunks:
        chunks = await retrieve_chunks(
            db=db,
            document_id=document_id,
            query_embedding=query_embedding,
            query_text=query,
            top_k=min(INTERVIEW_EVIDENCE_TOP_K, settings.top_k_max * 2),
            include_low_signal=False,
            section_types=None,
            doc_domain="job_description",
            source_types=source_types,
        )

    return [
        {
            "chunk_id": c["chunk_id"],
            "page_number": c["page_number"],
            "snippet": c["snippet"],
            "sourceType": c.get("sourceType", "jd"),
            "sourceTitle": c.get("sourceTitle", ""),
            "retrieval_source": c.get("retrieval_source"),
            "semantic_score": c.get("semantic_score"),
            "keyword_score": c.get("keyword_score"),
            "final_score": c.get("final_score"),
        }
        for c in chunks
    ]



async def _retrieve_evidence_for_competency(
    db: AsyncSession,
    document_id: uuid.UUID,
    competency_label: str,
) -> list[dict]:
    """Retrieve evidence for a competency label. sourceTypes=['jd'], topK=6."""
    query_embedding = embed_query(competency_label)
    chunks = await retrieve_chunks(
        db=db,
        document_id=document_id,
        query_embedding=query_embedding,
        query_text=competency_label,
        top_k=COMPETENCY_EVIDENCE_TOP_K,
        include_low_signal=False,
        section_types=None,
        doc_domain="job_description",
        source_types=["jd"],
    )
    return [_retrieval_dict_to_evidence_item(c) for c in chunks]


def _retrieval_dict_to_evidence_item(c: dict) -> dict:
    """Map a retrieve_chunks row into an interview evidence dict (snippet + section_type + text)."""
    cid = c.get("chunk_id") or c.get("chunkId") or ""
    raw = (c.get("text") or c.get("snippet") or "").strip()
    st = c.get("section_type")
    section_type = str(st).strip() if st not in (None, "") else "general"
    pg = c.get("page_number") if c.get("page_number") is not None else c.get("page")
    try:
        page_num = int(pg) if pg is not None else 0
    except (TypeError, ValueError):
        page_num = 0
    return {
        "chunk_id": cid,
        "chunkId": cid,
        "page_number": page_num,
        "page": page_num,
        "text": raw,
        "snippet": raw,
        "section_type": section_type,
        "sourceType": c.get("sourceType", "jd"),
        "sourceTitle": c.get("sourceTitle", ""),
        "retrieval_source": c.get("retrieval_source"),
        "semantic_score": c.get("semantic_score"),
        "keyword_score": c.get("keyword_score"),
        "final_score": c.get("final_score"),
    }


def _session_pool_query_text(role_profile: dict | None) -> str:
    """Stable, broad query for one vector retrieval per session (JD pool)."""
    rp = role_profile or {}
    focus = rp.get("focusAreas") or []
    parts = [
        " ".join(str(x) for x in focus if x),
        str(rp.get("domain") or ""),
        str(rp.get("seniority") or ""),
        "job responsibilities qualifications requirements skills experience role",
    ]
    return " ".join(p.strip() for p in parts if p and str(p).strip()).strip() or (
        "job description responsibilities qualifications requirements"
    )


def _token_overlap_score(query: str, doc_text: str) -> float:
    qt = set(re.findall(r"[a-zA-Z0-9]+", (query or "").lower()))
    ct = set(re.findall(r"[a-zA-Z0-9]+", (doc_text or "").lower()))
    if not qt or not ct:
        return 0.0
    inter = len(qt & ct)
    union = len(qt | ct) or 1
    return inter / union


def _rank_pool_for_query(pool: list[dict], query_text: str, top_k: int) -> list[dict]:
    """
    Pick top_k chunks from a session pool by lexical overlap with query_text, blended with
    retrieval final_score from the pool build (no extra vector DB query).
    """
    if not pool or top_k <= 0:
        return []
    scored: list[tuple[float, int, dict]] = []
    for i, item in enumerate(pool):
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or item.get("snippet") or "").strip()
        lex = _token_overlap_score(query_text, text)
        fs = item.get("final_score")
        try:
            fs_f = float(fs) if fs is not None else 0.0
        except (TypeError, ValueError):
            fs_f = 0.0
        fs_f = max(0.0, min(1.0, fs_f))
        combined = 0.62 * lex + 0.38 * fs_f
        scored.append((combined, -i, item))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [dict(t[2]) for t in scored[:top_k]]


async def _get_or_create_session_jd_pool(
    db: AsyncSession,
    document_id: uuid.UUID,
    session_id: uuid.UUID,
    role_profile: dict | None,
) -> list[dict]:
    """
    Cached top-K JD chunks for the session (one embed + retrieve per session until TTL expires).
    """
    cached = await asyncio.to_thread(session_pool_get, session_id)
    if isinstance(cached, list) and cached:
        return cached

    query_text = _session_pool_query_text(role_profile)
    query_embedding = embed_query(query_text)
    top_k = min(SESSION_JD_POOL_TOP_K, settings.top_k_max * 4)
    chunks = await retrieve_chunks(
        db=db,
        document_id=document_id,
        query_embedding=query_embedding,
        query_text=query_text,
        top_k=top_k,
        include_low_signal=False,
        section_types=None,
        doc_domain="job_description",
        source_types=["jd"],
    )
    result = [_retrieval_dict_to_evidence_item(c) for c in chunks]
    if result:
        await asyncio.to_thread(session_pool_set, session_id, result)
    return result


def _normalize_evaluation_chunk(e: dict) -> dict:
    """
    Canonical shape for evaluate_answer / citation generation:
    chunk_id, text, page_number, section_type; snippet mirrors text for scoring helpers.
    """
    cid = str(e.get("chunk_id") or e.get("chunkId") or "").strip()
    raw_text = (e.get("text") or e.get("snippet") or "").strip()
    pg = e.get("page_number") if e.get("page_number") is not None else e.get("page")
    try:
        page_number = int(pg) if pg is not None else 0
    except (TypeError, ValueError):
        page_number = 0
    st = e.get("section_type")
    section_type = str(st).strip() if st not in (None, "") else "general"
    return {
        "chunk_id": cid,
        "chunkId": cid,
        "text": raw_text,
        "snippet": raw_text,
        "page_number": page_number,
        "page": page_number,
        "section_type": section_type,
        "sourceType": str(e.get("sourceType", "jd")),
        "sourceTitle": str(e.get("sourceTitle", "")),
        **(
            {k: e[k] for k in ("retrieval_source", "semantic_score", "keyword_score", "final_score") if k in e}
        ),
    }


def normalize_evaluation_evidence(evidence: list[dict]) -> list[dict]:
    """Normalize rubric/retrieved chunks before the evaluation LLM and citation parsing."""
    out: list[dict] = []
    for e in evidence or []:
        if not isinstance(e, dict):
            continue
        n = _normalize_evaluation_chunk(e)
        if not n["text"].strip():
            continue
        out.append(n)
    return out
