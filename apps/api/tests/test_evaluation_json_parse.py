"""Unit tests for evaluation JSON parsing helpers."""

from app.services.interview import _loads_evaluation_json, _parse_evaluation_response


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
