"""Tests for POST /analyze-fit (schemas, rate limit path, response shaping)."""

import uuid

import pytest
from pydantic import ValidationError

from app.core.rate_limit import RATE_LIMITS, _path_to_route
from app.routers.analyze_fit import (
    AnalyzeFitGapOut,
    AnalyzeFitMatchOut,
    AnalyzeFitRecommendationOut,
    AnalyzeFitRequest,
    AnalyzeFitResponse,
)


def test_rate_limit_maps_analyze_fit_path():
    assert _path_to_route("/analyze-fit") == "analyze-fit"
    assert "analyze-fit" in RATE_LIMITS


def test_rate_limit_maps_analyze_fit_latest_path():
    assert _path_to_route("/analyze-fit/latest") == "fit-history"


def test_rate_limit_maps_fit_history_path():
    assert _path_to_route("/fit-history") == "fit-history"
    assert "fit-history" in RATE_LIMITS


def test_rate_limit_maps_user_resume_ask_path():
    assert _path_to_route("/user/resume/ask") == "ask"


def test_analyze_fit_request_accepts_string_uuids_and_optional_question():
    jd = str(uuid.uuid4())
    rs = str(uuid.uuid4())
    r = AnalyzeFitRequest(job_description_id=jd, resume_id=rs)
    assert r.job_description_id == jd
    assert r.resume_id == rs
    assert r.question is None

    r2 = AnalyzeFitRequest(job_description_id=jd, resume_id=rs, question="Focus on leadership?")
    assert r2.question == "Focus on leadership?"


def test_analyze_fit_request_rejects_empty_ids():
    with pytest.raises(ValidationError):
        AnalyzeFitRequest(job_description_id="", resume_id=str(uuid.uuid4()))


def test_analyze_fit_response_roundtrip():
    payload = AnalyzeFitResponse(
        matches=[
            AnalyzeFitMatchOut(
                requirement="Python",
                resume_evidence="5 years",
                confidence=0.85,
                importance="high",
            )
        ],
        gaps=[
            AnalyzeFitGapOut(
                requirement="Kubernetes",
                reason="Not in resume.",
                importance="medium",
            )
        ],
        fit_score=70,
        matched_count=1,
        total_requirements=2,
        gap_count=1,
        gap_penalty=2.5,
        coverage_raw=72.5,
        summary="Good Python; gap on K8s.",
        recommendations=[
            AnalyzeFitRecommendationOut(
                gap="Kubernetes",
                suggestion="Add kubectl/minikube and tie to your Docker work.",
                example_resume_line="Kubernetes (minikube) for local orchestration.",
            )
        ],
    )
    d = payload.model_dump()
    assert set(d.keys()) == {
        "matches",
        "gaps",
        "fit_score",
        "matched_count",
        "total_requirements",
        "gap_count",
        "gap_penalty",
        "coverage_raw",
        "summary",
        "recommendations",
    }
    assert d["fit_score"] == 70
    assert d["matched_count"] == 1
    assert d["total_requirements"] == 2
    assert len(d["recommendations"]) == 1
