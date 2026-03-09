"""Pure service tests for gap analysis helpers."""

from types import SimpleNamespace

from app.services.gap_analysis_comparison import (
    build_requirement_targets,
    build_resume_query,
    classify_requirement_match,
)
from app.services.gap_analysis_explanation import summarize_gap_analysis
from app.services.resume_intelligence import build_resume_profile_from_chunks


def test_build_resume_profile_from_chunks_preserves_chunk_refs():
    profile = build_resume_profile_from_chunks(
        [
            {
                "chunk_id": "chunk-1",
                "page": 1,
                "text": "Python engineer with AWS Certified background and 5 years experience.",
                "skills_detected": ["python", "aws"],
            }
        ],
        "Resume",
    )

    assert any(item["label"].lower() == "python" for item in profile["skills"])
    assert any(item["label"].lower() == "aws" for item in profile["cloudPlatforms"])
    assert profile["experienceClaims"][0]["years"] == 5
    assert profile["skills"][0]["evidence"][0]["chunkId"] == "chunk-1"


def test_build_requirement_targets_prefers_existing_jd_intelligence():
    document = SimpleNamespace(
        jd_extraction_json={
            "required_skills": ["python"],
            "preferred_skills": ["spark"],
            "tools": ["docker"],
            "cloud_platforms": ["aws"],
            "experience_years_required": "5+ years of experience",
            "education_requirements": "Bachelor's degree in Computer Science",
        },
        role_profile={"focusAreas": ["backend engineering"]},
        competencies=[
            {
                "id": "leadership",
                "label": "Leadership",
                "description": "Lead projects",
                "evidence": [{"chunkId": "jd-1", "page": 1, "sourceTitle": "JD"}],
            }
        ],
    )

    targets = build_requirement_targets(document)
    labels = {item["label"].lower() for item in targets}
    assert "python" in labels
    assert "spark" in labels
    assert "docker" in labels
    assert "aws" in labels
    assert "leadership" in labels


def test_classify_requirement_match_uses_raw_resume_evidence():
    target = {"type": "skill", "label": "Python", "aliases": []}
    resume_evidence = [
        {
            "chunkId": "resume-1",
            "snippet": "Built Python APIs and automation workflows.",
            "page": 1,
            "sourceTitle": "Resume",
            "sourceType": "resume",
        }
    ]

    result = classify_requirement_match(target, resume_evidence)
    assert result["status"] == "match"
    assert "explicitly mentions" in result["reason"]


def test_build_resume_query_uses_helper_cache_only_for_expansion():
    target = {"label": "Python", "aliases": [], "type": "skill"}
    helper_profiles = [
        {"skills": [{"label": "Python", "normalized": "python", "evidence": []}]}
    ]

    query = build_resume_query(target, helper_profiles)
    assert "Python" in query


def test_summarize_gap_analysis_returns_cited_summary():
    summary = summarize_gap_analysis(
        [
            {
                "label": "Python",
                "importance": "required",
                "status": "match",
                "reason": "Resume evidence explicitly mentions Python.",
                "resume_evidence": [{"chunkId": "resume-1", "page": 1, "sourceTitle": "Resume", "sourceType": "resume"}],
                "jd_evidence": [],
            },
            {
                "label": "Kubernetes",
                "importance": "required",
                "status": "gap",
                "reason": "No supporting resume evidence was retrieved for this requirement.",
                "resume_evidence": [],
                "jd_evidence": [{"chunkId": "jd-1", "page": 1, "sourceTitle": "JD", "sourceType": "jd"}],
            },
        ]
    )

    assert summary["overall_alignment_score"] >= 0
    assert summary["strengths_cited"]
    assert summary["gaps_cited"]
