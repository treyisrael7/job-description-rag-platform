"""Types and lookup tables for chunk retrieval."""

import re
from typing import Literal

RetrievalMode = Literal["hybrid", "semantic", "keyword"]

Scope = Literal["union", "primary", "additional"]

# Token / cost guard for production retrieval: cap chunks sent to LLMs (see retrieve_chunks).
MAX_RETRIEVAL_CHUNKS = 8

# Backward compat: expand canonical section types to legacy job description section names in DB
SECTION_TYPE_EXPANSION: dict[str, list[str]] = {
    "tools": ["tools", "tools_technologies"],
    "qualifications": ["qualifications", "preferred_qualifications"],
    "about": ["about", "position_summary", "company_info"],
    "other": ["other", "location", "company_info"],
}

# Query keywords -> suggested section types (canonical: responsibilities, qualifications, tools, compensation, about, other)
QUERY_SECTION_HINTS: dict[str, list[str]] = {
    "skill": ["qualifications", "tools"],
    "qualification": ["qualifications"],
    "responsibilit": ["responsibilities"],
    "requirement": ["qualifications"],
    "salary": ["compensation"],
    "salaries": ["compensation"],
    "pay": ["compensation"],
    "compensation": ["compensation"],
    "benefits": ["compensation"],
    "wage": ["compensation"],
    "how much": ["compensation"],
    "location": ["about", "other"],
    "remote": ["about", "other"],
    "company": ["about", "other"],
    "role": ["about"],
    "job": ["about"],
    "tool": ["tools"],
    "tech": ["tools"],
}

KEYWORD_VARIANT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bfront\s*-\s*end\b|\bfrontend\b", re.IGNORECASE), '(frontend OR "front-end")'),
    (re.compile(r"\bback\s*-\s*end\b|\bbackend\b", re.IGNORECASE), '(backend OR "back-end")'),
    (re.compile(r"\bfull\s*-\s*stack\b|\bfull\s+stack\b", re.IGNORECASE), '("full stack" OR "full-stack")'),
]

KEYWORD_TECH_SYNONYMS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<!\w)c\+\+(?!\w)", re.IGNORECASE), '("c++" OR cpp)'),
    (re.compile(r"(?<!\w)c#(?!\w)", re.IGNORECASE), '("c#" OR csharp)'),
    (re.compile(r"(?<!\w)(?:\.net|dotnet)(?!\w)", re.IGNORECASE), '(".net" OR dotnet)'),
    (re.compile(r"(?<!\w)(?:node\.js|nodejs)(?!\w)", re.IGNORECASE), '("node.js" OR nodejs)'),
    (re.compile(r"(?<!\w)(?:next\.js|nextjs)(?!\w)", re.IGNORECASE), '("next.js" OR nextjs)'),
    (re.compile(r"(?<!\w)(?:react\.js|reactjs)(?!\w)", re.IGNORECASE), '("react.js" OR reactjs)'),
    (re.compile(r"(?<!\w)(?:postgresql|postgres)(?!\w)", re.IGNORECASE), "(postgresql OR postgres)"),
    (re.compile(r"(?<!\w)pgvector(?!\w)", re.IGNORECASE), '(pgvector OR "pg vector")'),
    (re.compile(r"(?<!\w)aws(?!\w)", re.IGNORECASE), '(aws OR "amazon web services")'),
]
