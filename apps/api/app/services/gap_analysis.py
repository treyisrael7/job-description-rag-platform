"""Orchestration service for resume-to-JD gap analysis."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document
from app.services.gap_analysis_comparison import (
    build_requirement_targets,
    build_resume_query,
    classify_requirement_match,
)
from app.services.gap_analysis_explanation import summarize_gap_analysis
from app.services.gap_analysis_retrieval import (
    resolve_resume_sources,
    retrieve_jd_evidence_for_target,
    retrieve_resume_evidence_for_target,
)


def _normalize_jd_evidence(items: list[dict] | None) -> list[dict]:
    normalized = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        chunk_id = item.get("chunkId") or item.get("chunk_id")
        if not chunk_id:
            continue
        normalized.append(
            {
                "chunkId": str(chunk_id),
                "page": item.get("page") or item.get("page_number"),
                "snippet": item.get("snippet", ""),
                "sourceTitle": item.get("sourceTitle", ""),
                "sourceType": item.get("sourceType", "jd"),
                "retrieval_source": item.get("retrieval_source"),
                "semantic_score": item.get("semantic_score"),
                "keyword_score": item.get("keyword_score"),
                "final_score": item.get("final_score"),
            }
        )
    return normalized


async def generate_gap_analysis(
    db: AsyncSession,
    *,
    document: Document,
    user_id: uuid.UUID,
) -> dict:
    """Generate a retrieval-backed gap analysis for one JD document."""
    resume_context = await resolve_resume_sources(db, document.id, user_id)
    resume_sources = resume_context["sources"]
    if not resume_sources:
        return {
            "summary": "No resume source is available for comparison.",
            "overall_alignment_score": 0,
            "matched_requirements": [],
            "partial_requirements": [],
            "gap_requirements": [],
            "strengths_cited": [],
            "gaps_cited": [],
            "resume_sources_considered": [],
        }

    helper_profiles = [
        source.profile_json
        for source in resume_sources
        if isinstance(source.profile_json, dict)
    ]
    targets = build_requirement_targets(document)
    compared = []

    for target in targets:
        jd_evidence = _normalize_jd_evidence(target.get("jd_evidence"))
        if not jd_evidence:
            jd_query = " ".join(
                part
                for part in [target["label"], target.get("description") or ""]
                if part
            )
            jd_evidence = await retrieve_jd_evidence_for_target(db, document.id, jd_query, top_k=3)

        resume_query = build_resume_query(target, helper_profiles) or target["label"]
        resume_evidence = await retrieve_resume_evidence_for_target(
            db,
            document.id,
            resume_query,
            additional_document_ids=resume_context["additional_document_ids"],
            top_k=4,
        )
        classification = classify_requirement_match(target, resume_evidence)
        compared.append(
            {
                "id": target["id"],
                "type": target["type"],
                "label": target["label"],
                "importance": target["importance"],
                "description": target.get("description"),
                "status": classification["status"],
                "reason": classification["reason"],
                "confidence": classification["confidence"],
                "jd_evidence": jd_evidence,
                "resume_evidence": resume_evidence,
            }
        )

    explanation = summarize_gap_analysis(compared)

    return {
        "summary": explanation["summary"],
        "overall_alignment_score": explanation["overall_alignment_score"],
        "matched_requirements": [item for item in compared if item["status"] == "match"],
        "partial_requirements": [item for item in compared if item["status"] == "partial"],
        "gap_requirements": [item for item in compared if item["status"] == "gap"],
        "strengths_cited": explanation["strengths_cited"],
        "gaps_cited": explanation["gaps_cited"],
        "resume_sources_considered": [
            {
                "sourceId": str(source.id),
                "title": source.title,
                "documentId": str(source.document_id),
            }
            for source in resume_sources
        ],
    }
