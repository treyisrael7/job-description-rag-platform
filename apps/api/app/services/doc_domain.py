"""Doc domain detection: general vs job_description."""

import re

# Canonical section types (used across job description and general docs)
SECTION_TYPES = frozenset(
    {"responsibilities", "qualifications", "tools", "compensation", "about", "other"}
)

# Job description signals: if >=2 found in text, treat as job_description
JD_SIGNAL_PATTERNS = [
    r"\bresponsibilities\b",
    r"\bqualifications\b",
    r"\brequired\b",
    r"\bpreferred\b",
    r"\bsalary\b",
    r"\bposition\s+summary\b",
    r"\babout\s+the\s+role\b",
    r"\bkey\s+responsibilities\b",
    r"\bminimum\s+qualifications\b",
    r"\bjob\s+summary\b",
    r"\bwhat\s+you['']ll\s+do\b",
    r"\brequirements\b",
]


def detect_doc_domain(full_text: str) -> str:
    """
    Auto-detect doc_domain from extracted text.
    Returns 'job_description' if >=2 job description signals found, else 'general'.
    """
    if not full_text or len(full_text.strip()) < 50:
        return "general"
    text_lower = full_text.lower()
    matches = 0
    for pat in JD_SIGNAL_PATTERNS:
        if re.search(pat, text_lower, re.IGNORECASE):
            matches += 1
            if matches >= 2:
                return "job_description"
    return "general"


# Map jd_sections canonical names -> user-facing section types
JD_TO_CANONICAL_SECTION: dict[str, str] = {
    "responsibilities": "responsibilities",
    "qualifications": "qualifications",
    "preferred_qualifications": "qualifications",
    "tools_technologies": "tools",
    "compensation": "compensation",
    "about": "about",
    "position_summary": "about",
    "location": "other",
    "company_info": "other",
}


def normalize_section_type(section_type: str | None) -> str:
    """Map job description section types to canonical 6 values. Returns 'other' for unknown."""
    if not section_type:
        return "other"
    return JD_TO_CANONICAL_SECTION.get(section_type.strip().lower(), "other")
