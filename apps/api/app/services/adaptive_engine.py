"""Adaptive question-type selection from session performance aggregates."""

from __future__ import annotations

import math
import random
from typing import Any, Mapping

_WEAK = 0.6
_STRONG = 0.75
_DEFAULT = 0.5

_DIMENSIONS: tuple[str, ...] = ("technical", "behavioral", "communication")

# Maps performance dimension → next question type when that dimension is targeted.
_DIMENSION_TO_QUESTION_TYPE: dict[str, str] = {
    "technical": "technical",
    "behavioral": "behavioral",
    "communication": "behavioral_followup",
}

# UI / API: human-readable line for session header (deterministic; no random tie-break).
_FOCUS_LABELS: dict[str, str] = {
    "technical": "Technical Skills",
    "behavioral": "Behavioral Skills",
    "behavioral_followup": "Communication & Follow-up",
    "hard": "Advanced Challenge",
}


def _next_kind_deterministic(s: dict[str, float]) -> str:
    """Same priority as :func:`select_next_question_type` except weakest-band uses fixed dimension order."""
    if s["technical"] < _WEAK:
        return "technical"
    if s["behavioral"] < _WEAK:
        return "behavioral"
    if s["communication"] < _WEAK:
        return "behavioral_followup"
    if all(s[d] > _STRONG for d in _DIMENSIONS):
        return "hard"
    m = min(s[d] for d in _DIMENSIONS)
    for d in _DIMENSIONS:
        if s[d] == m:
            return _DIMENSION_TO_QUESTION_TYPE[d]
    return "behavioral"


def adaptive_focus_label(performance_profile: Mapping[str, Any] | None) -> str | None:
    """
    Short label for UI (e.g. "Behavioral Skills") derived from ``performance_profile``.

    Mirrors :func:`select_next_question_type` thresholds; weakest band picks the first
    tied-weakest dimension in technical → behavioral → communication order (stable for UI).
    Returns ``None`` if profile is missing or empty.
    """
    if not performance_profile or not isinstance(performance_profile, dict) or not performance_profile:
        return None
    kind = _next_kind_deterministic(_scores(performance_profile))
    return _FOCUS_LABELS.get(kind)


def _coerce_score(raw: Any) -> float:
    if isinstance(raw, bool):
        return _DEFAULT
    if isinstance(raw, (int, float)):
        x = float(raw)
        if math.isfinite(x):
            return x
    return _DEFAULT


def _scores(profile: Mapping[str, Any] | None) -> dict[str, float]:
    p = profile or {}
    return {d: _coerce_score(p.get(d)) for d in _DIMENSIONS}


def select_next_question_type(performance_profile: Mapping[str, Any] | None) -> str:
    """
    Choose the next interview question category from a session ``performance_profile``.

    Checks (in order) ``technical``, ``behavioral``, then ``communication`` against
    :data:`_WEAK` (0.6). If every dimension is above :data:`_STRONG` (0.75), returns
    ``hard``. Otherwise picks uniformly at random among the weakest dimension(s) and
    maps them to question types (communication → ``behavioral_followup``).

    Missing or non-numeric values use 0.5, consistent with
    :func:`app.services.performance_profile.compute_performance_profile` defaults.
    """
    s = _scores(performance_profile)

    if s["technical"] < _WEAK:
        return "technical"
    if s["behavioral"] < _WEAK:
        return "behavioral"
    if s["communication"] < _WEAK:
        return "behavioral_followup"

    if all(s[d] > _STRONG for d in _DIMENSIONS):
        return "hard"

    m = min(s[d] for d in _DIMENSIONS)
    weakest = [d for d in _DIMENSIONS if s[d] == m]
    chosen = random.choice(weakest)
    return _DIMENSION_TO_QUESTION_TYPE[chosen]
