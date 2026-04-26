"""POST /analyze-fit: JD + resume retrieval and structured fit analysis."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import assert_resource_ownership, get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import Document, FitAnalysis, User
from app.services.analyze_fit_retrieval import augment_analyze_fit_chunks_with_resume_education
from app.services.analyze_fit_service import (
    analyze_fit as run_analyze_fit,
    compute_fit_score,
)
from app.services.fit_analysis_cache import (
    DEFAULT_ANALYZE_FIT_QUESTION,
    analyze_fit_query_fingerprint,
    document_chunk_fingerprints,
    fetch_latest_cached_fit_analysis,
    normalize_analyze_fit_question,
)
from app.services.retrieval import embed_query, retrieve_chunks, suggest_section_filters

router = APIRouter(prefix="/analyze-fit", tags=["analyze-fit"])
logger = logging.getLogger(__name__)

ANALYZE_FIT_TOP_K = 8
_DEFAULT_QUESTION = DEFAULT_ANALYZE_FIT_QUESTION


class AnalyzeFitRequest(BaseModel):
    job_description_id: str = Field(
        ...,
        min_length=1,
        description="UUID of the job description document (primary retrieval target).",
    )
    resume_id: str = Field(
        ...,
        min_length=1,
        description="UUID of the resume document (additional retrieval target).",
    )
    question: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional focus for embedding and analysis; default broad fit query.",
    )


class AnalyzeFitMatchOut(BaseModel):
    requirement: str
    resume_evidence: str
    confidence: float
    importance: str


class AnalyzeFitGapOut(BaseModel):
    requirement: str
    reason: str
    importance: str


class AnalyzeFitRecommendationOut(BaseModel):
    gap: str
    suggestion: str
    missing_keywords: list[str] = Field(default_factory=list)
    bullet_rewrite: str = ""
    example_resume_line: str


class AnalyzeFitResponse(BaseModel):
    matches: list[AnalyzeFitMatchOut]
    gaps: list[AnalyzeFitGapOut]
    fit_score: int
    matched_count: int = 0
    total_requirements: int = 0
    gap_count: int = 0
    gap_penalty: float = 0.0
    coverage_raw: float = 0.0
    summary: str
    recommendations: list[AnalyzeFitRecommendationOut]


class AnalyzeFitLatestResponse(BaseModel):
    """Saved analysis for current JD + resume *content* (chunk fingerprints must match)."""

    has_analysis: bool
    analysis: AnalyzeFitResponse | None = None
    created_at: str | None = None
    cache_hit_default_question: bool = Field(
        default=False,
        description="True when the returned row used the default broad question fingerprint.",
    )


def _parse_uuid(label: str, raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw).strip())
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {label}: {raw!r}",
        ) from None


def _analyze_fit_response_from_row(row: FitAnalysis) -> AnalyzeFitResponse:
    matches = list(row.matches_json) if isinstance(row.matches_json, list) else []
    gaps = list(row.gaps_json) if isinstance(row.gaps_json, list) else []
    recs = list(row.recommendations_json) if isinstance(row.recommendations_json, list) else []
    score_meta = compute_fit_score(matches, gaps)
    return AnalyzeFitResponse(
        matches=[AnalyzeFitMatchOut(**m) for m in matches],
        gaps=[AnalyzeFitGapOut(**g) for g in gaps],
        fit_score=int(row.fit_score),
        matched_count=int(score_meta["matched_count"]),
        total_requirements=int(score_meta["total_requirements"]),
        gap_count=int(score_meta["gap_count"]),
        gap_penalty=float(score_meta["gap_penalty"]),
        coverage_raw=float(score_meta["coverage_raw"]),
        summary=row.summary or "",
        recommendations=[AnalyzeFitRecommendationOut(**r) for r in recs],
    )


@router.get("/latest", response_model=AnalyzeFitLatestResponse)
async def analyze_fit_latest(
    job_description_id: str = Query(..., min_length=1),
    resume_id: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the most recent saved analyze-fit result for this JD + resume **only if**
    chunk fingerprints still match (same ingested content). Prefers the default broad
    question when multiple rows exist. No LLM call.
    """
    jd_id = _parse_uuid("job_description_id", job_description_id)
    rs_id = _parse_uuid("resume_id", resume_id)
    if jd_id == rs_id:
        raise HTTPException(status_code=422, detail="job_description_id and resume_id must differ")

    result = await db.execute(select(Document).where(Document.id == jd_id))
    jd_doc = result.scalar_one_or_none()
    if not jd_doc:
        raise HTTPException(status_code=404, detail="Job description document not found")
    assert_resource_ownership(jd_doc, current_user)

    result = await db.execute(select(Document).where(Document.id == rs_id))
    resume_doc = result.scalar_one_or_none()
    if not resume_doc:
        raise HTTPException(status_code=404, detail="Resume document not found")
    assert_resource_ownership(resume_doc, current_user)

    try:
        jd_fp, resume_fp = await document_chunk_fingerprints(db, jd_id, rs_id)
    except Exception as e:
        logger.exception("analyze-fit/latest document_chunk_fingerprints failed")
        raise HTTPException(
            status_code=503,
            detail=f"Could not load document chunks: {str(e)[:200]}",
        ) from e

    stmt = (
        select(FitAnalysis)
        .where(
            FitAnalysis.user_id == current_user.id,
            FitAnalysis.job_description_id == jd_id,
            FitAnalysis.resume_id == rs_id,
            FitAnalysis.jd_chunk_fingerprint == jd_fp,
            FitAnalysis.resume_chunk_fingerprint == resume_fp,
        )
        .order_by(FitAnalysis.created_at.desc())
    )
    rows = list((await db.execute(stmt)).scalars().all())
    if not rows:
        return AnalyzeFitLatestResponse(has_analysis=False)

    default_fp = analyze_fit_query_fingerprint(normalize_analyze_fit_question(None))
    chosen = next((r for r in rows if r.query_fingerprint == default_fp), rows[0])
    return AnalyzeFitLatestResponse(
        has_analysis=True,
        analysis=_analyze_fit_response_from_row(chosen),
        created_at=chosen.created_at.isoformat(),
        cache_hit_default_question=chosen.query_fingerprint == default_fp,
    )


@router.post("", response_model=AnalyzeFitResponse)
async def analyze_fit_endpoint(
    body: AnalyzeFitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve chunks from the job description and resume, then run deterministic-scored
    fit analysis (matches, gaps, recommendations). Separate from ``/ask`` (Q&A JSON).

    Repeating the same user, documents, question, and chunk content returns a cached
    row (skips embedding, retrieval, and LLM). Re-ingestion changes chunk fingerprints
    and forces a fresh analysis.
    """
    jd_id = _parse_uuid("job_description_id", body.job_description_id)
    resume_id = _parse_uuid("resume_id", body.resume_id)

    if jd_id == resume_id:
        raise HTTPException(
            status_code=422,
            detail="job_description_id and resume_id must differ",
        )

    result = await db.execute(select(Document).where(Document.id == jd_id))
    jd_doc = result.scalar_one_or_none()
    if not jd_doc:
        raise HTTPException(status_code=404, detail="Job description document not found")
    assert_resource_ownership(jd_doc, current_user)
    if jd_doc.status != "ready":
        raise HTTPException(
            status_code=400,
            detail=f"Job description must be ready; current status: {jd_doc.status}",
        )

    result = await db.execute(select(Document).where(Document.id == resume_id))
    resume_doc = result.scalar_one_or_none()
    if not resume_doc:
        raise HTTPException(status_code=404, detail="Resume document not found")
    assert_resource_ownership(resume_doc, current_user)
    if resume_doc.status != "ready":
        raise HTTPException(
            status_code=400,
            detail=f"Resume must be ready; current status: {resume_doc.status}",
        )

    normalized_q = normalize_analyze_fit_question(body.question)
    query_fp = analyze_fit_query_fingerprint(normalized_q)

    try:
        jd_chunk_fp, resume_chunk_fp = await document_chunk_fingerprints(db, jd_id, resume_id)
    except Exception as e:
        logger.exception("analyze-fit document_chunk_fingerprints failed")
        raise HTTPException(
            status_code=503,
            detail=f"Could not load document chunks for cache: {str(e)[:200]}",
        ) from e

    cached = await fetch_latest_cached_fit_analysis(
        db,
        user_id=current_user.id,
        job_description_id=jd_id,
        resume_id=resume_id,
        query_fingerprint=query_fp,
        jd_chunk_fingerprint=jd_chunk_fp,
        resume_chunk_fingerprint=resume_chunk_fp,
    )
    if cached is not None:
        logger.info(
            "analyze-fit cache hit user_id=%s job_description_id=%s resume_id=%s",
            current_user.id,
            jd_id,
            resume_id,
        )
        matches = list(cached.matches_json) if isinstance(cached.matches_json, list) else []
        gaps = list(cached.gaps_json) if isinstance(cached.gaps_json, list) else []
        recs = (
            list(cached.recommendations_json)
            if isinstance(cached.recommendations_json, list)
            else []
        )
        score_meta = compute_fit_score(matches, gaps)
        return AnalyzeFitResponse(
            matches=[AnalyzeFitMatchOut(**m) for m in matches],
            gaps=[AnalyzeFitGapOut(**g) for g in gaps],
            fit_score=int(cached.fit_score),
            matched_count=int(score_meta["matched_count"]),
            total_requirements=int(score_meta["total_requirements"]),
            gap_count=int(score_meta["gap_count"]),
            gap_penalty=float(score_meta["gap_penalty"]),
            coverage_raw=float(score_meta["coverage_raw"]),
            summary=cached.summary or "",
            recommendations=[AnalyzeFitRecommendationOut(**r) for r in recs],
        )

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API not configured; set OPENAI_API_KEY",
        )

    q = normalized_q

    try:
        query_embedding = embed_query(q)
    except Exception as e:
        logger.exception("analyze-fit embed_query failed")
        raise HTTPException(status_code=503, detail=f"Embedding failed: {str(e)[:200]}") from e

    section_types = None
    doc_domain = jd_doc.doc_domain or None
    if jd_doc.doc_domain == "job_description":
        section_types = suggest_section_filters(q)

    top_k = min(ANALYZE_FIT_TOP_K, settings.top_k_max)

    try:
        chunks = await retrieve_chunks(
            db=db,
            document_id=jd_id,
            query_embedding=query_embedding,
            query_text=q,
            top_k=top_k,
            include_low_signal=False,
            section_types=section_types,
            doc_domain=doc_domain,
            additional_document_ids=[resume_id],
        )
        if not chunks and section_types:
            chunks = await retrieve_chunks(
                db=db,
                document_id=jd_id,
                query_embedding=query_embedding,
                query_text=q,
                top_k=top_k,
                include_low_signal=False,
                section_types=None,
                doc_domain=doc_domain,
                additional_document_ids=[resume_id],
            )
    except Exception as e:
        logger.exception("analyze-fit retrieve_chunks failed")
        raise HTTPException(status_code=503, detail=f"Retrieval failed: {str(e)[:200]}") from e

    chunks = await augment_analyze_fit_chunks_with_resume_education(
        db,
        resume_id=resume_id,
        chunks=chunks,
    )

    try:
        raw = run_analyze_fit(query=q, retrieved_chunks=chunks, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("analyze-fit run_analyze_fit failed")
        raise HTTPException(status_code=503, detail=f"Analysis failed: {str(e)[:200]}") from e

    db.add(
        FitAnalysis(
            user_id=current_user.id,
            job_description_id=jd_id,
            resume_id=resume_id,
            fit_score=int(raw["fit_score"]),
            matches_json=raw["matches"],
            gaps_json=raw["gaps"],
            recommendations_json=raw["recommendations"],
            summary=str(raw.get("summary") or ""),
            query_fingerprint=query_fp,
            jd_chunk_fingerprint=jd_chunk_fp,
            resume_chunk_fingerprint=resume_chunk_fp,
        )
    )

    return AnalyzeFitResponse(
        matches=[AnalyzeFitMatchOut(**m) for m in raw["matches"]],
        gaps=[AnalyzeFitGapOut(**g) for g in raw["gaps"]],
        fit_score=raw["fit_score"],
        matched_count=int(raw.get("matched_count") or 0),
        total_requirements=int(raw.get("total_requirements") or 0),
        gap_count=int(raw.get("gap_count") or 0),
        gap_penalty=float(raw.get("gap_penalty") or 0.0),
        coverage_raw=float(raw.get("coverage_raw") or 0.0),
        summary=raw["summary"],
        recommendations=[AnalyzeFitRecommendationOut(**r) for r in raw["recommendations"]],
    )
