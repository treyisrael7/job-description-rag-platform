"""Pydantic models and constants for interview API."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


QUESTION_MIX_PRESETS = {
    "balanced": {"behavioral": 40, "roleSpecific": 30, "scenario": 30},
    "behavioral_heavy": {"behavioral": 60, "roleSpecific": 25, "scenario": 15},
    "scenario_heavy": {"behavioral": 25, "roleSpecific": 25, "scenario": 50},
}


class InterviewGenerateInput(BaseModel):
    document_id: uuid.UUID
    difficulty: str = Field("junior", pattern="^(junior|mid|senior)$")
    num_questions: int = Field(8, ge=1, le=10)
    domain_override: str | None = None
    seniority_override: str | None = None
    question_mix_preset: str | None = None


class EvidenceItem(BaseModel):
    chunk_id: str
    page_number: int
    snippet: str


class InterviewQuestionOutput(BaseModel):
    id: uuid.UUID
    type: str
    focus_area: str = ""
    competency_id: str | None = None
    competency_label: str | None = None
    question: str
    key_topics: list[str] = []
    evidence: list[EvidenceItem]
    rubric_bullets: list[str]
    last_answer_id: uuid.UUID | None = None
    evaluation_json: dict[str, Any] | None = None


class InterviewGenerateOutput(BaseModel):
    session_id: uuid.UUID
    questions: list[InterviewQuestionOutput]


class InterviewEvaluateInput(BaseModel):
    document_id: uuid.UUID
    question_id: uuid.UUID
    answer_text: str = Field(..., min_length=1)
    mode: Literal["lite", "full"] = Field(
        "full",
        description='lite: score + short feedback only. full: strengths, gaps, improved answer, citations.',
    )


class EvidenceUsedItem(BaseModel):
    quote: str
    sourceId: str
    sourceType: str | None = None
    sourceTitle: str | None = None
    page: int | None = None
    chunkId: str | None = None


class CitationItem(BaseModel):
    chunkId: str
    page: int | None = None
    sourceTitle: str = ""
    sourceType: str = "jd"


class CitedItem(BaseModel):
    text: str
    citations: list[CitationItem] = []


class StrengthEvalItem(BaseModel):
    text: str
    evidence: str = Field("", description="Direct quote from the candidate's answer supporting this strength.")
    highlight: str = Field("", description="Verbatim phrase from the candidate's answer (for UI emphasis).")
    impact: str = Field("", description="Why this strength is valuable for the role (tie to JD/rubric/competency).")


class GapEvalItem(BaseModel):
    text: str = Field(..., description="What the candidate said (from their answer).")
    missing: str = Field("", description="What is absent or weak vs rubric/JD.")
    expected: str = Field("", description="Relevant JD/rubric requirement (explicitly referenced).")
    jd_alignment: str = Field(
        "",
        description="How the answer does or does not match the job requirement.",
    )
    improvement: str = Field("", description="Specific phrasing they should say instead.")


class EvaluationCitationOut(BaseModel):
    chunk_id: str
    page_number: int = 0
    text: str = ""


class ScoreBreakdownOut(BaseModel):
    relevance_to_context: int
    completeness: int
    clarity: int
    jd_alignment: int
    overall: int


class RubricScoreItem(BaseModel):
    """Per JD dimension: score on 0–10 and reasoning that explains that score."""

    name: str
    score: float = Field(..., ge=0.0, le=10.0, description="Dimension score on a 0–10 scale.")
    reasoning: str = Field(
        ...,
        min_length=1,
        description="Explains why this score was assigned for this dimension (answer + role fit).",
    )


class EvaluationUsageOut(BaseModel):
    """Monthly evaluation usage after this request (UTC month)."""

    plan: str = Field(..., description="User plan key (free, pro, enterprise).")
    evaluations_used_this_month: int = Field(
        ...,
        ge=0,
        description="Count including the evaluation just completed.",
    )
    evaluation_limit: int = Field(
        ...,
        ge=0,
        description="Maximum evaluations allowed this month for this plan.",
    )


class InterviewEvaluateOutput(BaseModel):
    answer_id: uuid.UUID
    evaluation_mode: Literal["lite", "full"] = Field(
        "full",
        description="lite: compact scoring; full: explainable evaluation with strengths/gaps.",
    )
    score: float = Field(..., description="Rubric aggregate (0–100).")
    llm_score: float = Field(..., description="Model-reported score on a 0–10 scale.")
    summary: str = Field(
        "",
        description="2–3 sentence model explanation of why the score was given.",
    )
    score_reasoning: str = Field(
        "",
        description=(
            "1–2 sentences why this score was given, explicitly tying strengths and gaps to rubric expectations."
        ),
    )
    score_breakdown: ScoreBreakdownOut
    feedback_summary: str
    strengths: list[StrengthEvalItem]
    gaps: list[GapEvalItem]
    citations: list[EvaluationCitationOut] = []
    strengths_cited: list[CitedItem] = []
    gaps_cited: list[CitedItem] = []
    improved_answer: str = Field(
        "",
        description=(
            "Rewrite of the candidate’s answer into a stronger version that would score 9–10/10: "
            "keep the original idea, add depth, tools/metrics when relevant, realistic not generic."
        ),
    )
    follow_up_questions: list[str]
    suggested_followup: str | None = None
    evidence_used: list[EvidenceUsedItem]
    rubric_scores: list[RubricScoreItem] = Field(
        default_factory=list,
        description="Per-dimension scores (0–10) with reasoning; aligns with document rubric when present.",
    )
    evaluation_json: dict[str, Any] = Field(
        default_factory=dict,
        description="Stored snapshot: score, strengths, gaps, citations, rubric_scores, and optional extra keys.",
    )
    usage: EvaluationUsageOut = Field(
        ...,
        description="Plan and monthly evaluation quota usage (after this call).",
    )


class RoleProfileOut(BaseModel):
    domain: str
    seniority: str
    roleTitleGuess: str = ""
    focusAreas: list[str] = []
    questionMix: dict = {}


class RubricDimensionOut(BaseModel):
    name: str
    description: str = ""


class SessionSummary(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    mode: str
    difficulty: str
    created_at: str
    question_count: int
    role_profile: RoleProfileOut | None = None


class SessionDetail(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    document_id: uuid.UUID
    mode: str
    difficulty: str
    created_at: str
    questions: list[InterviewQuestionOutput]
    role_profile: RoleProfileOut | None = None
    performance_profile: dict | None = None
    adaptive_focus_label: str | None = None
    rubric_json: list[RubricDimensionOut] | None = None


class QuestionDetail(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    type: str
    focus_area: str = ""
    competency_id: str | None = None
    competency_label: str | None = None
    question: str
    key_topics: list[str]
    evidence: list[EvidenceItem]
    rubric_bullets: list[str]
    created_at: str
    last_answer_id: uuid.UUID | None = None
    evaluation_json: dict[str, Any] | None = None


class ScoreTrendPoint(BaseModel):
    at: str
    score: float
    question_id: uuid.UUID


class CompetencyStats(BaseModel):
    competency_id: str | None = None
    competency_label: str
    average_score: float
    answer_count: int


class ImprovementSummary(BaseModel):
    answer_count: int
    first_half_average: float | None = None
    second_half_average: float | None = None
    improvement_delta: float | None = None


class InterviewSessionAnalytics(BaseModel):
    session_id: uuid.UUID
    answer_count: int
    average_score: float | None
    score_trend: list[ScoreTrendPoint]
    strongest_competencies: list[CompetencyStats]
    weakest_competencies: list[CompetencyStats]
    improvement: ImprovementSummary


class GlobalScoreTrendPoint(BaseModel):
    at: str
    score: float
    session_id: uuid.UUID
    question_id: uuid.UUID


class RecentSessionAnalyticsRow(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    created_at: str
    difficulty: str
    question_count: int
    answer_count: int
    average_score: float | None


class InterviewRetrievalFeedbackInput(BaseModel):
    """Report that JD/resume retrieval for an evaluation felt wrong (optional note + chunk snapshot)."""

    document_id: uuid.UUID
    answer_id: uuid.UUID
    reason: str | None = Field(None, max_length=4000)
    retrieval_chunk_ids: list[str] | None = Field(
        None,
        description="Chunk UUID strings shown with the evaluation; server fills from stored feedback if omitted.",
    )

    @field_validator("reason", mode="before")
    @classmethod
    def _strip_reason(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            s = value.strip()
            return s or None
        return value

    @field_validator("retrieval_chunk_ids", mode="before")
    @classmethod
    def _normalize_chunk_ids(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, list):
            raise TypeError("retrieval_chunk_ids must be a list of strings")
        out: list[str] = []
        seen: set[str] = set()
        for item in value[:80]:
            if not isinstance(item, str):
                raise TypeError("each retrieval_chunk_id must be a string")
            tid = item.strip()
            if not tid or tid in seen:
                continue
            if len(tid) > 128:
                raise ValueError("retrieval_chunk_id too long")
            seen.add(tid)
            out.append(tid)
        return out


class InterviewRetrievalFeedbackOutput(BaseModel):
    id: uuid.UUID
    updated: bool = Field(..., description="True if an existing row for this answer was overwritten.")


class InterviewAnalyticsOverview(BaseModel):
    total_session_count: int
    total_answer_count: int
    overall_average_score: float | None
    score_trend: list[GlobalScoreTrendPoint]
    strongest_competencies: list[CompetencyStats]
    weakest_competencies: list[CompetencyStats]
    recent_sessions: list[RecentSessionAnalyticsRow]
    last_session_vs_prior_percent_change: float | None
    focus_area_hint: str | None
