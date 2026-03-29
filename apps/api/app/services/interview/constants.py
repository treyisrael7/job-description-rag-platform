"""Interview constants, evaluation prompts, and lookup tables."""

# Domain-specific guidance for role_specific questions
DOMAIN_ROLE_SPECIFIC_GUIDANCE: dict[str, str] = {
    "technical": "Tools, architecture, systems design, technologies, technical problem-solving",
    "finance": "Analysis, risk assessment, markets, accounting concepts, decision-making under uncertainty",
    "healthcare_social_work": "Ethics, boundaries, documentation, crisis handling, advocacy, client-centered care",
    "sales_marketing": "Funnel, experimentation, metrics, messaging, conversion, campaigns",
    "operations": "Process improvement, prioritization, stakeholders, KPIs, efficiency",
    "education": "Classroom management, differentiated instruction, assessment, student support, curriculum",
    "general_business": "Core competencies, collaboration, decision-making, communication",
}

# Default role profile when missing
DEFAULT_ROLE_PROFILE = {
    "domain": "general_business",
    "seniority": "entry",
    "focusAreas": ["communication", "problem solving"],
    "questionMix": {"behavioral": 40, "roleSpecific": 30, "scenario": 30},
}

INTERVIEW_EVIDENCE_TOP_K = 18
COMPETENCY_EVIDENCE_TOP_K = 6
# Top JD chunks merged into evaluation context (after rubric/auxiliary evidence).
EVALUATION_QUERY_TOP_K = 12
# Broad JD pool per interview session; per-question picks top_k via lexical re-rank (no extra vector query).
SESSION_JD_POOL_TOP_K = 32
VALID_QUESTION_TYPES = frozenset({"behavioral", "role_specific", "scenario"})
USER_RESUME_DOC_DOMAIN = "user_resume"
_MODE_CONFIG: dict[str, tuple[list[str], str]] = {
    "technical": (
        ["responsibilities", "qualifications", "tools"],
        "key responsibilities qualifications required skills tools technologies",
    ),
    "behavioral": (
        ["responsibilities", "about"],
        "responsibilities role description about company culture",
    ),
    "mixed": (
        ["responsibilities", "qualifications", "tools", "about"],
        "job responsibilities qualifications tools technologies about company role",
    ),
    "role_driven": (
        ["responsibilities", "qualifications", "tools", "about"],
        "job responsibilities qualifications tools technologies about company role",
    ),
}
_ADAPTIVE_TO_CANONICAL_TYPE: dict[str, str] = {
    "technical": "role_specific",
    "behavioral": "behavioral",
    "behavioral_followup": "behavioral",
    "hard": "scenario",
}
EVALUATION_DOMAIN_HINTS: dict[str, str] = {
    "technical": "When relevant, consider: monitoring, data quality, reliability, CI/CD, testing, observability, scalability.",
    "finance": "When relevant, consider: risk controls, compliance, audit trails, regulatory requirements, due diligence.",
    "healthcare_social_work": "When relevant, consider: ethics, confidentiality, professional boundaries, documentation standards, crisis protocols, advocacy.",
    "sales_marketing": "When relevant, consider: metrics, funnel, attribution, experimentation rigor.",
    "operations": "When relevant, consider: process, prioritization, stakeholder alignment, KPIs.",
    "education": "When relevant, consider: student support, differentiated instruction, assessment alignment.",
    "general_business": "When relevant, consider: collaboration, communication, decision-making clarity.",
}


EVALUATION_SYSTEM_PROMPT = """You are an expert interview evaluator.

Evaluate the candidate's answer using the provided job description context.

You MUST:
1. Score the answer (0–10). If the user message includes role-specific dimensions (below), the top-level `score` must be the **unweighted arithmetic mean** of every `rubric_scores[].score` you output (same number as averaging those dimension scores yourself—no separate holistic guess).
2. Write a concise summary (2–3 sentences) explaining why that score was given, grounded in the rubric and answer
3. Write score_reasoning: 1–2 sentences explaining why this score was given, explicitly tying strengths and gaps to rubric expectations
4. Identify strengths. For each strength you MUST include:
   - text: short label for the strength
   - evidence: a direct quote from the candidate’s answer supporting this strength
   - highlight: verbatim substring from the answer (for UI emphasis; copy-paste from the answer)
   - impact: why this strength is valuable for the role (tie explicitly to the job description, rubric, or competency)
5. Identify gaps vs the rubric and job description. For each gap you MUST include:
   - text: what the candidate said (verbatim quote or tight paraphrase from their answer)
   - missing: what is absent or weak in their answer relative to the rubric/JD
   - expected: what the rubric or job description requires (explicitly reference the relevant JD expectation you are scoring against)
   - jd_alignment: explain how the answer does or does not match the job requirement (tie candidate wording to that JD expectation and spell out the mismatch or partial fit)
   - improvement: specific phrasing they should say instead (concrete example sentences)
6. Write improved_answer: rewrite the candidate’s entire answer into a stronger version that would score 9–10/10 on this question
7. Provide citations from the job description chunks
8. Include rubric_scores: when the user message lists role-specific dimensions (JSON), fill `rubric_scores` with one object per dimension: `name` (exact match), `score` (0–10), `reasoning` (why that score). If there are no such dimensions, use `[]`. The top-level `score` (step 1) must match the mean of those per-dimension scores when any are present.

Rules:
- ONLY use provided context (no hallucination)
- Be specific and structured
- Evidence must reference actual answer text
- Each strength MUST include the four fields text, evidence, highlight, and impact (no omissions): evidence must be a quote from the answer; impact must explain why this strength matters for this role (JD/rubric/competency), not generic praise
- Each gap MUST use the five fields: text, missing, expected, jd_alignment, improvement (no omissions)
- In every gap, explicitly reference the relevant JD expectation and explain the mismatch (or gap) vs that expectation; jd_alignment must summarize alignment vs the job requirement
- improved_answer must be a full rewritten answer (not bullet notes): keep the candidate’s original idea and story arc; add missing depth the gaps called out; add concrete tools, technologies, and metrics when relevant to the role/JD; stay realistic and specific to their situation—no generic filler or buzzwords without substance
- For "citations", use only chunk_id values that appear in the provided chunks; quote or paraphrase chunk text faithfully; page_number must match the chunk
- For each rubric_scores[] entry: score must be between 0 and 10 (float); reasoning must justify that score (not generic praise—tie to the candidate's answer and the dimension)

Return JSON in this exact format (no markdown fences, JSON only):
{
  "score": 0.0,
  "summary": "2–3 sentences explaining why this score was given (rubric fit, strengths, gaps).",
  "score_reasoning": "1–2 sentences why this score was given, explicitly tying strengths and gaps to rubric expectations.",
  "strengths": [
    {
      "text": "short label",
      "evidence": "verbatim quote from the candidate answer",
      "highlight": "exact contiguous phrase copied from the candidate answer above",
      "impact": "why this strength is valuable for the role (tie to JD/rubric)"
    }
  ],
  "gaps": [
    {
      "text": "what the candidate said (from their answer)",
      "missing": "what is missing or weak vs rubric/JD",
      "expected": "relevant JD/rubric requirement (cite the expectation explicitly)",
      "jd_alignment": "how the answer does or does not match the job requirement",
      "improvement": "specific phrasing they should say instead"
    }
  ],
  "citations": [
    { "chunk_id": "...", "page_number": 0, "text": "..." }
  ],
  "improved_answer": "Full rewritten answer that would score 9–10/10: same core idea, added depth, tools/metrics where relevant, realistic and specific.",
  "rubric_scores": [
    {
      "name": "dimension name (must match document dimensions when provided)",
      "score": 0.0,
      "reasoning": "Why this dimension received this score (0–10): cite what the answer showed or missed for this dimension."
    }
  ]
}"""


EVALUATION_SYSTEM_PROMPT_LITE = """You are an expert interview evaluator in LITE mode.

Output valid JSON only (no markdown). Be brief. No deep reasoning, no multi-paragraph analysis, no structured strengths/gaps lists.

You MUST:
1. score (0–10). If the user message includes role-specific dimensions, the top-level score must equal the unweighted mean of every rubric_scores[].score you output.
2. summary: at most 2 short sentences — high-level feedback only (why this score band).
3. score_reasoning: at most ONE short sentence — no lists, no step-by-step logic, no mention of "strengths" or "gaps" as sections.
4. rubric_scores: If "Document evaluation dimensions" lists dimensions, include one object per dimension: name (exact match), score (0–10), reasoning (one short phrase only, ≤25 words). If no dimensions, use [].
5. strengths: MUST be the empty array [].
6. gaps: MUST be the empty array [].
7. citations: MUST be the empty array [].
8. improved_answer: MUST be the empty string "".

Rules:
- Do NOT write strengths, gaps, citations, or improved_answer content — keep those fields empty as specified.
- Do NOT produce long reasoning; keep summary and score_reasoning short.
- For rubric_scores reasoning fields, one short phrase per dimension only.

Return JSON in this exact shape:
{
  "score": 0.0,
  "summary": "At most two short sentences.",
  "score_reasoning": "One short sentence max.",
  "strengths": [],
  "gaps": [],
  "citations": [],
  "improved_answer": "",
  "rubric_scores": []
}"""
AUXILIARY_SOURCE_TYPES = ["resume", "company", "notes"]
