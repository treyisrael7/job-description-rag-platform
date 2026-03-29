"""Query text normalization for PostgreSQL full-text retrieval."""

import re

from app.services.retrieval.constants import (
    KEYWORD_TECH_SYNONYMS,
    KEYWORD_VARIANT_PATTERNS,
    QUERY_SECTION_HINTS,
)


def suggest_section_filters(query: str) -> list[str] | None:
    """If query suggests specific sections, return section_types to filter."""
    q = query.lower().strip()
    words = set(re.findall(r"\b\w+\b", q))
    suggested: set[str] = set()
    for hint, sections in QUERY_SECTION_HINTS.items():
        if hint in q or any(hint in w for w in words):
            suggested.update(sections)
    return list(suggested) if suggested else None


def _normalize_keyword_query_text(query_text: str) -> str:
    """
    Light preprocessing for PostgreSQL full-text retrieval.

    Goals:
    - collapse punctuation/whitespace noise common in user questions
    - preserve important technical tokens used in job descriptions
    - add a few hand-maintained spelling/format variants that improve keyword recall
    """
    normalized = query_text.strip()
    if not normalized:
        return ""

    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    normalized = re.sub(r"[^\S\r\n]+", " ", normalized)
    normalized = re.sub(r"[?!,:;()\[\]{}]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    for pattern, replacement in KEYWORD_TECH_SYNONYMS:
        normalized = pattern.sub(f" {replacement} ", normalized)
    for pattern, replacement in KEYWORD_VARIANT_PATTERNS:
        normalized = pattern.sub(f" {replacement} ", normalized)

    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized
