"""Lightweight checks that uploaded PDF text looks like a resume or CV, not arbitrary documents."""

from __future__ import annotations

import re

# Need this many weighted hits from resume-like signals (not all required).
_MIN_RESUME_SCORE = 3

# Strong markers that the file is a job description / posting, not a personal resume.
_JD_MARKERS: list[re.Pattern[str]] = [
    re.compile(r"\bresponsibilities\b", re.IGNORECASE),
    re.compile(r"\bqualifications\b", re.IGNORECASE),
    re.compile(r"\bwe\s+are\s+(?:seeking|hiring|looking)\b", re.IGNORECASE),
    re.compile(r"\bapply\s+(?:now|today)\b", re.IGNORECASE),
    re.compile(r"\bequal\s+opportunity\b", re.IGNORECASE),
    re.compile(r"\bbenefits\s+include\b", re.IGNORECASE),
    re.compile(r"\bthe\s+company\b", re.IGNORECASE),
    re.compile(r"\bposition\s+summary\b", re.IGNORECASE),
]

# Typical resume / CV content (any several together suggest a resume).
_RESUME_SIGNALS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\bexperience\b|\bemployment\b|\bwork\s+history\b", re.IGNORECASE), 1),
    (re.compile(r"\beducation\b|\buniversity\b|\bdegree\b|\bbachelor\b|\bmaster\b|\bph\.?\s*d\b", re.IGNORECASE), 1),
    (re.compile(r"\bskills\b|\btechnical\s+skills\b|\bcore\s+competenc", re.IGNORECASE), 1),
    (re.compile(r"\bprofessional\s+summary\b|\bcareer\s+objective\b|\babout\s+me\b", re.IGNORECASE), 1),
    (re.compile(r"\b(curriculum\s+vitae|(^|\s)cv(\s|$)|\brésumé|\bresume\b)", re.IGNORECASE), 1),
    (re.compile(r"\b\d+\s*\+?\s*years?\s+(?:of\s+)?(?:experience|exp\.?)\b", re.IGNORECASE), 1),
    (re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE), 1),
    (re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b"), 1),
    (re.compile(r"\blinkedin\.com/\b", re.IGNORECASE), 1),
    (re.compile(r"\bprojects?\b.*\b(?:github|gitlab)\b|\bportfolio\b", re.IGNORECASE), 1),
]


def validate_resume_text(text: str) -> None:
    """
    Raise ValueError with a user-facing message if ``text`` is unlikely to be a resume or CV.

    Heuristics are intentionally loose (typical sections, contact hints, anti job-posting).
    """
    raw = (text or "").strip()
    if len(raw) < 200:
        raise ValueError(
            "This PDF has very little text. Please upload a readable resume or CV PDF."
        )

    normalized = raw.lower()

    jd_hits = sum(1 for p in _JD_MARKERS if p.search(normalized))
    if jd_hits >= 2:
        raise ValueError(
            "This file looks like a job posting or employer document, not your own resume. "
            "Upload your CV or resume PDF instead."
        )

    score = sum(w for pat, w in _RESUME_SIGNALS if pat.search(normalized))

    if score < _MIN_RESUME_SCORE:
        raise ValueError(
            "This PDF doesn't look like a resume or CV. It should include typical sections "
            "such as experience, education, skills, or contact information."
        )
