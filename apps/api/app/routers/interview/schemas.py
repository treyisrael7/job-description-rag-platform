"""Pydantic models and constants for interview API."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


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


class InterviewEvaluateOutput(BaseModel):
    answer_id: uuid.UUID
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
    evaluation_json: dict[str, Any] = Field(
        default_factory=dict,
        description="Stored snapshot: score, strengths, gaps, citations (and optional extra keys).",
    )


class RoleProfileOut(BaseModel):
    domain: str
    seniority: str
    roleTitleGuess: str = ""
    focusAreas: list[str] = []
    questionMix: dict = {}


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
