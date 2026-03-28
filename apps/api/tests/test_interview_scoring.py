"""Tests for interview answer scoring helpers."""

from app.services.interview_scoring import build_feedback_summary, score_from_rubric_dimension_mean


def test_score_from_rubric_dimension_mean_unweighted_average() -> None:
    mean_0_10, breakdown = score_from_rubric_dimension_mean(
        [
            {"name": "A", "score": 6, "reasoning": ""},
            {"name": "B", "score": 8, "reasoning": ""},
        ]
    )
    assert mean_0_10 == 7.0
    assert breakdown is not None
    assert breakdown["overall"] == 70
    assert breakdown["relevance_to_context"] == 70
    assert breakdown["aggregation"] == "rubric_dimension_mean"
    assert breakdown["n_rubric_dimensions"] == 2


def test_score_from_rubric_dimension_mean_empty() -> None:
    assert score_from_rubric_dimension_mean([]) == (None, None)
    assert score_from_rubric_dimension_mean([{}]) == (None, None)


def test_build_feedback_summary_rubric_mean() -> None:
    s = build_feedback_summary(
        {
            "aggregation": "rubric_dimension_mean",
            "overall": 72,
            "n_rubric_dimensions": 5,
            "relevance_to_context": 72,
            "completeness": 72,
            "clarity": 72,
            "jd_alignment": 72,
        }
    )
    assert "72/100" in s
    assert "5" in s
    assert "equally" in s.lower() or "mean" in s.lower()
