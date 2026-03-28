"""Unit tests for evaluation JSON parsing helpers."""

from app.services.interview import (
    _loads_evaluation_json,
    _parse_evaluation_response,
    normalize_rubric_scores_output,
)


def test_loads_evaluation_json_strips_markdown_fence() -> None:
    s = """```json
{"score": 7, "summary": "ok", "strengths": [], "gaps": []}
```"""
    d = _loads_evaluation_json(s)
    assert d["score"] == 7


def test_loads_evaluation_json_trailing_comma() -> None:
    s = '{"score": 6, "strengths": [], "gaps": [],}'
    d = _loads_evaluation_json(s)
    assert d["score"] == 6


def test_loads_evaluation_json_extra_prose() -> None:
    s = 'Here: {"score": 8, "summary": "x", "strengths": [], "gaps": []} tail'
    d = _loads_evaluation_json(s)
    assert d["score"] == 8


def test_parse_evaluation_response_fallback_on_garbage() -> None:
    ev = [{"chunk_id": "c1", "text": "t", "page_number": 1}]
    out = _parse_evaluation_response("not json at all {{{", ev)
    assert out["score"] == 5.0
    assert "could not be read" in out["summary"].lower()
    assert out.get("score_reasoning") == ""
    assert out.get("rubric_scores") == []


def test_parse_evaluation_response_rubric_scores() -> None:
    ev = [{"chunk_id": "c1", "text": "t", "page_number": 1}]
    raw = """{"score": 7, "summary": "ok", "score_reasoning": "r", "strengths": [], "gaps": [],
    "citations": [], "improved_answer": "",
    "rubric_scores": [{"name": "Financial Modeling", "score": 8, "reasoning": "Solid"}]}"""
    out = _parse_evaluation_response(raw, ev)
    assert len(out["rubric_scores"]) == 1
    assert out["rubric_scores"][0]["name"] == "Financial Modeling"
    assert out["rubric_scores"][0]["score"] == 8.0
    assert out["rubric_scores"][0]["reasoning"] == "Solid"


def test_normalize_rubric_scores_clamps_and_fills_reasoning() -> None:
    out = normalize_rubric_scores_output(
        [
            {"name": "Dim A", "score": 11, "reasoning": "Too high"},
            {"name": "Dim B", "score": 3, "reasoning": ""},
        ]
    )
    assert out[0]["score"] == 10.0
    assert out[0]["reasoning"] == "Too high"
    assert out[1]["score"] == 3.0
    assert len(out[1]["reasoning"]) > 10
    assert "Dim B" in out[1]["reasoning"]
