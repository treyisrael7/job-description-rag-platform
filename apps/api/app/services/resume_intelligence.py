"""Helper-layer resume profile extraction from raw resume chunks."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentChunk, InterviewSource
from app.services.jd_extraction import CLOUD_KEYWORDS, SKILL_KEYWORDS, TOOL_KEYWORDS

EXPERIENCE_RE = re.compile(r"(?P<years>\d+)\s*\+?\s*years?", re.IGNORECASE)
DEGREE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bph\.?d\b|\bdoctorate\b", re.IGNORECASE), "PhD"),
    (re.compile(r"\bmaster'?s\b|\bm\.?s\.?\b|\bmba\b", re.IGNORECASE), "Master's degree"),
    (re.compile(r"\bbachelor'?s\b|\bb\.?s\.?\b|\bb\.?a\.?\b", re.IGNORECASE), "Bachelor's degree"),
    (re.compile(r"\bassociate'?s\b", re.IGNORECASE), "Associate's degree"),
]
CERTIFICATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\baws certified\b", re.IGNORECASE), "AWS Certified"),
    (re.compile(r"\bazure certified\b", re.IGNORECASE), "Azure Certified"),
    (re.compile(r"\bgcp certified\b|\bgoogle cloud certified\b", re.IGNORECASE), "Google Cloud Certified"),
    (re.compile(r"\bpmp\b", re.IGNORECASE), "PMP"),
    (re.compile(r"\bscrum master\b", re.IGNORECASE), "Scrum Master"),
]


def _normalize_term(value: str) -> str:
    text = re.sub(r"[^a-z0-9#+.\s-]+", " ", value.lower())
    return re.sub(r"\s+", " ", text).strip()


def _evidence_ref(chunk: dict, title: str) -> dict:
    return {
        "chunkId": str(chunk["chunk_id"]),
        "page": chunk.get("page"),
        "sourceTitle": title,
        "sourceType": "resume",
    }


def _add_term(bucket: dict[str, dict], label: str, chunk: dict, title: str) -> None:
    normalized = _normalize_term(label)
    if not normalized:
        return
    entry = bucket.setdefault(
        normalized,
        {"label": label.strip(), "normalized": normalized, "evidence": []},
    )
    evidence = _evidence_ref(chunk, title)
    if evidence["chunkId"] not in {item["chunkId"] for item in entry["evidence"]}:
        entry["evidence"].append(evidence)


def build_resume_profile_from_chunks(chunks: list[dict], title: str) -> dict:
    """Build a helper cache from resume chunks while preserving raw chunk references."""
    skills: dict[str, dict] = {}
    tools: dict[str, dict] = {}
    clouds: dict[str, dict] = {}
    education: dict[str, dict] = {}
    certifications: dict[str, dict] = {}
    experience_claims: dict[int, dict] = {}

    for chunk in chunks:
        text = chunk.get("text", "")
        lower_text = text.lower()

        for detected in chunk.get("skills_detected") or []:
            term = str(detected).strip()
            if term:
                _add_term(skills, term, chunk, title)

        for term in SKILL_KEYWORDS:
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lower_text, re.IGNORECASE):
                _add_term(skills, term, chunk, title)
        for term in TOOL_KEYWORDS:
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lower_text, re.IGNORECASE):
                _add_term(tools, term, chunk, title)
        for term in CLOUD_KEYWORDS:
            if term in lower_text:
                canonical = "gcp" if term == "google cloud" else term
                _add_term(clouds, canonical, chunk, title)

        for years_match in EXPERIENCE_RE.finditer(text):
            years = int(years_match.group("years"))
            entry = experience_claims.setdefault(
                years,
                {"label": f"{years}+ years", "years": years, "evidence": []},
            )
            evidence = _evidence_ref(chunk, title)
            if evidence["chunkId"] not in {item["chunkId"] for item in entry["evidence"]}:
                entry["evidence"].append(evidence)

        for pattern, label in DEGREE_PATTERNS:
            if pattern.search(text):
                _add_term(education, label, chunk, title)

        for pattern, label in CERTIFICATION_PATTERNS:
            if pattern.search(text):
                _add_term(certifications, label, chunk, title)

    return {
        "cachedFromChunks": True,
        "skills": sorted(skills.values(), key=lambda item: item["label"].lower()),
        "tools": sorted(tools.values(), key=lambda item: item["label"].lower()),
        "cloudPlatforms": sorted(clouds.values(), key=lambda item: item["label"].lower()),
        "experienceClaims": sorted(experience_claims.values(), key=lambda item: item["years"], reverse=True),
        "education": sorted(education.values(), key=lambda item: item["label"].lower()),
        "certifications": sorted(certifications.values(), key=lambda item: item["label"].lower()),
    }


async def extract_resume_profile(db: AsyncSession, source_id: uuid.UUID) -> dict | None:
    """Refresh the helper-layer profile_json for a resume source."""
    source_result = await db.execute(
        select(InterviewSource).where(InterviewSource.id == source_id)
    )
    source = source_result.scalar_one_or_none()
    if not source or source.source_type != "resume":
        return None

    chunk_result = await db.execute(
        select(
            DocumentChunk.id,
            DocumentChunk.page_number,
            DocumentChunk.content,
            DocumentChunk.skills_detected,
        )
        .where(DocumentChunk.source_id == source_id)
        .order_by(DocumentChunk.chunk_index.asc())
    )
    rows = chunk_result.all()
    if not rows:
        source.profile_json = None
        await db.flush()
        return None

    chunks = [
        {
            "chunk_id": row.id,
            "page": row.page_number,
            "text": row.content,
            "skills_detected": row.skills_detected or [],
        }
        for row in rows
    ]
    profile = build_resume_profile_from_chunks(chunks, source.title)
    source.profile_json = profile
    await db.flush()
    return profile
