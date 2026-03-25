"""Aggregate interview answer scores into a session-level performance profile."""

from __future__ import annotations

import math
from typing import Any, Mapping

DEFAULT_SCORE = 0.5

# Dimension keys treated as technical signal (subset of scores_json).
_TECHNICAL_DIMENSION_KEYS = frozenset(
    {
        "technical",
        "problem_solving",
        "correctness",
        "domain",
        "domain_knowledge",
        "jd_alignment",
    }
)

_COMMUNICATION_KEYS = frozenset({"communication", "clarity"})


def _normalize_question_type(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw).strip().lower()


def _get_scores_dict(scores_json: Any) -> dict[str, Any]:
    if scores_json is None:
        return {}
    if isinstance(scores_json, Mapping):
        return dict(scores_json)
    return {}


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return None
        return float(value)
    return None


def _all_numeric_scores(scores: Mapping[str, Any]) -> list[float]:
    out: list[float] = []
    for v in scores.values():
        x = _coerce_float(v)
        if x is not None:
            out.append(x)
    return out


def _scores_for_keys(scores: Mapping[str, Any], keys: frozenset[str]) -> list[float]:
    out: list[float] = []
    for k, v in scores.items():
        if str(k).strip().lower() in keys:
            x = _coerce_float(v)
            if x is not None:
                out.append(x)
    return out


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


# Stored interview answers keep rubric dimensions under feedback_json.score_breakdown.
# Omit ``overall`` here so session-level ``overall`` is a mean of dimensions, not diluted by a duplicate aggregate.
_SCORE_BREAKDOWN_KEYS_FOR_PROFILE = (
    "relevance_to_context",
    "completeness",
    "clarity",
    "jd_alignment",
)


def profile_answer_from_feedback(
    question_type: str | None,
    feedback_json: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Build a dict suitable for :func:`compute_performance_profile` from a stored answer row.

    Uses ``question_type`` and numeric rubric dimensions from ``feedback_json["score_breakdown"]``.
    """
    qt = _normalize_question_type(question_type)
    fb = dict(feedback_json) if isinstance(feedback_json, Mapping) else {}
    breakdown = fb.get("score_breakdown")
    scores: dict[str, Any] = {}
    if isinstance(breakdown, Mapping):
        for key in _SCORE_BREAKDOWN_KEYS_FOR_PROFILE:
            x = _coerce_float(breakdown.get(key))
            if x is not None:
                scores[key] = x
    return {"question_type": qt, "scores_json": scores}


def _resolve_answer(answer: Any) -> tuple[str, dict[str, Any]]:
    """Support dict-like rows and objects with question_type / scores_json."""
    if isinstance(answer, Mapping):
        qt = answer.get("question_type")
        sj = answer.get("scores_json")
    else:
        qt = getattr(answer, "question_type", None)
        sj = getattr(answer, "scores_json", None)
    return _normalize_question_type(qt), _get_scores_dict(sj)


def compute_performance_profile(answers: list[Any] | None) -> dict[str, float]:
    """
    Aggregate per-answer scores into category averages.

    Each answer should expose ``question_type`` (e.g. ``behavioral``, ``technical``) and
    ``scores_json`` (flat dimension name -> numeric score).

    - *technical*: average of scores whose dimension keys are technical-related.
    - *behavioral*: average of all numeric scores on answers whose type is behavioral.
    - *communication*: average of ``communication`` and ``clarity`` across all answers.
    - *overall*: average of every numeric score in every ``scores_json``.

    Categories with no contributing values default to ``0.5``. Empty ``answers`` yields
    all defaults.
    """
    if not answers:
        return {
            "technical": DEFAULT_SCORE,
            "behavioral": DEFAULT_SCORE,
            "communication": DEFAULT_SCORE,
            "overall": DEFAULT_SCORE,
        }

    technical_vals: list[float] = []
    behavioral_vals: list[float] = []
    communication_vals: list[float] = []
    overall_vals: list[float] = []

    for answer in answers:
        qtype, scores = _resolve_answer(answer)
        overall_vals.extend(_all_numeric_scores(scores))
        technical_vals.extend(_scores_for_keys(scores, _TECHNICAL_DIMENSION_KEYS))
        communication_vals.extend(_scores_for_keys(scores, _COMMUNICATION_KEYS))
        if qtype == "behavioral":
            behavioral_vals.extend(_all_numeric_scores(scores))

    def _bucket(avg: float | None) -> float:
        return DEFAULT_SCORE if avg is None else float(avg)

    return {
        "technical": _bucket(_avg(technical_vals)),
        "behavioral": _bucket(_avg(behavioral_vals)),
        "communication": _bucket(_avg(communication_vals)),
        "overall": _bucket(_avg(overall_vals)),
    }
