"""Tests that mock interview difficulty reaches generation and evaluation prompts."""

from app.services.interview.evaluation import _build_domain_aware_evaluation_prompt
from app.services.interview.questions import _build_domain_aware_prompt


def test_question_generation_prompt_includes_interview_difficulty():
    system_prompt, user_prompt = _build_domain_aware_prompt(
        {
            "domain": "technical",
            "seniority": "senior",
            "focusAreas": ["Python"],
            "questionMix": {"behavioral": 30, "roleSpecific": 40, "scenario": 30},
            "interviewDifficulty": "senior",
        },
        [{"chunk_id": "c1", "page_number": 1, "snippet": "Own Python platform strategy."}],
        3,
    )

    assert "INTERVIEW DIFFICULTY: senior" in system_prompt
    assert "ambiguity" in system_prompt.lower()
    assert "tradeoffs" in system_prompt.lower()
    assert "Generate exactly 3 questions" in user_prompt


def test_evaluation_prompt_includes_interview_difficulty_expectations():
    system_prompt, user_prompt = _build_domain_aware_evaluation_prompt(
        question="Describe your platform leadership.",
        question_type="role_specific",
        focus_area="Python",
        competency_label="Platform ownership",
        what_good_looks_like=["Explains tradeoffs", "Shows impact"],
        must_mention=[],
        evidence=[
            {
                "chunk_id": "c1",
                "page_number": 2,
                "snippet": "Role requires technical leadership and prioritization.",
            }
        ],
        role_profile={
            "domain": "technical",
            "seniority": "senior",
            "interviewDifficulty": "senior",
        },
        answer_text="I led a platform migration.",
    )

    assert system_prompt
    assert "Interview difficulty: senior" in user_prompt
    assert "leadership" in user_prompt.lower()
    assert "measurable impact" in user_prompt.lower()

