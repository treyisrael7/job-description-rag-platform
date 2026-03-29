"""Interview question generation (per-competency and domain-aware batch)."""

import json
import logging
import re
import uuid

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import InterviewQuestion, InterviewSession
from app.services.adaptive_engine import select_next_question_type
from app.services.jd_sections import normalize_jd_text
from app.services.interview.constants import (
    DEFAULT_ROLE_PROFILE,
    DOMAIN_ROLE_SPECIFIC_GUIDANCE,
    VALID_QUESTION_TYPES,
    _ADAPTIVE_TO_CANONICAL_TYPE,
)
from app.services.interview.evidence import _retrieve_evidence_for_competency
from app.services.interview.feedback import _feedback_from_answer_row, _format_feedback_lines

logger = logging.getLogger(__name__)

def _prompt_question_type(canonical_type: str, adaptive_target: str | None) -> str:
    """
    User-facing question type label injected into the generation prompt.
    Matches adaptive_engine outputs; maps mix-based canonical types when not adaptive.
    """
    if adaptive_target in ("technical", "behavioral", "behavioral_followup", "hard"):
        return adaptive_target
    if canonical_type == "behavioral":
        return "behavioral"
    if canonical_type == "role_specific":
        return "technical"
    if canonical_type == "scenario":
        return "hard"
    return "behavioral"

def _generate_single_question(
    competency_id: str,
    competency_label: str,
    canonical_question_type: str,
    evidence: list[dict],
    role_profile: dict,
    adaptive_target: str | None = None,
    last_answer_feedback: dict[str, list[str]] | None = None,
) -> dict | None:
    """Generate one question for a competency using its evidence. Returns None if no evidence.

    ``canonical_question_type`` is stored on the question row (behavioral | role_specific | scenario).
    The prompt injects ``question_type`` (technical | behavioral | behavioral_followup | hard) via
    :func:`_prompt_question_type`.

    For ``behavioral_followup``, ``last_answer_feedback`` may contain ``strengths`` and ``gaps`` from
    the most recent evaluated answer in the session.
    """
    if not evidence or not settings.openai_api_key:
        return None

    from app.services.jd_sections import normalize_jd_text

    excerpt_lines = []
    for i, e in enumerate(evidence):
        snippet = normalize_jd_text(e.get("snippet", "")).strip()
        excerpt_lines.append(f"[{i}] {snippet}")

    excerpts_text = "\n\n".join(excerpt_lines)
    domain = role_profile.get("domain", "general_business")
    seniority = role_profile.get("seniority", "entry")
    seniority_hint = "entry-level" if seniority == "entry" else "mid-level" if seniority == "mid" else "senior-level"

    question_type = _prompt_question_type(canonical_question_type, adaptive_target)

    followup_context = ""
    user_followup = ""
    if question_type == "behavioral_followup":
        fb = last_answer_feedback or {}
        strengths_items = [str(x).strip() for x in (fb.get("strengths") or []) if str(x).strip()]
        gaps_items = [str(x).strip() for x in (fb.get("gaps") or []) if str(x).strip()]
        strengths_txt = _format_feedback_lines(strengths_items)
        gaps_txt = _format_feedback_lines(gaps_items)
        followup_context = f"""

PRIOR ANSWER FEEDBACK (target the follow-up):
Strengths noted: {strengths_txt}

The candidate previously showed weaknesses in: {gaps_txt}

Generate a follow-up question that specifically probes this weakness."""
        user_followup = """

The follow-up must directly address the weaknesses above; if none were recorded, infer a plausible gap from the competency and JD and still probe deeply."""

    system_prompt = f"""You are generating an interview question.

Question type: {question_type}

- If technical: focus on role-specific technical skills
- If behavioral: ask STAR-style questions
- If behavioral_followup: ask a deeper probing follow-up question based on previous answer weaknesses
- If hard: increase difficulty, ambiguity, or depth

Ground all questions in the provided job description context.

Competency: "{competency_label}"
SENIORITY: {seniority} ({seniority_hint})
DOMAIN: {domain}{followup_context}

RULES:
1. Follow the question type above; shape the line of questioning as: behavioral / role-specific skills / scenario as appropriate to that type.
2. The question MUST be grounded in the job description excerpts in the user message.
3. whatGoodLooksLike: 2-4 bullets describing what a strong answer covers.
4. Output valid JSON only: {{"question": "...", "whatGoodLooksLike": ["...","..."]}}"""

    user_content = f"""Competency: {competency_label}

Job description context:
{excerpts_text}

Generate exactly one interview question per the system instructions (question type: {question_type}).{user_followup}
Output JSON only."""

    try:
        from openai import OpenAI

        # Single-question generation: MODEL_FAST only (cheap path).
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.model_fast,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=400,
        )
        raw = (response.choices[0].message.content or "").strip()
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            raw = json_match.group(0)
        data = json.loads(raw)
        question_text = str(data.get("question", "")).strip()
        what_good = data.get("whatGoodLooksLike")
        if isinstance(what_good, list):
            what_good = [str(x).strip() for x in what_good if x]
        else:
            what_good = []

        evidence_for_q = [
            {
                "chunk_id": str(e.get("chunk_id") or e.get("chunkId") or ""),
                "page_number": int(e.get("page_number") or e.get("page") or 0),
                "snippet": str(e.get("snippet", "")),
                "sourceType": e.get("sourceType", "jd"),
                "sourceTitle": e.get("sourceTitle", ""),
                "retrieval_source": e.get("retrieval_source"),
                "semantic_score": e.get("semantic_score"),
                "keyword_score": e.get("keyword_score"),
                "final_score": e.get("final_score"),
            }
            for e in evidence
        ]

        return {
            "type": canonical_question_type,
            "competencyId": competency_id,
            "competencyLabel": competency_label,
            "questionText": question_text,
            "whatGoodLooksLike": what_good,
            "evidence": evidence_for_q,
            "evidenceChunkIds": [str(e.get("chunk_id") or e.get("chunkId", "")) for e in evidence],
        }
    except Exception as e:
        logger.warning("_generate_single_question failed for %s: %s", competency_label, e)
        return None


async def generate_questions(
    db: AsyncSession,
    document_id: uuid.UUID,
    num_questions: int,
    role_profile: dict,
    competencies: list[dict],
    session_id: uuid.UUID | None = None,
) -> list[dict]:
    """
    Generate questions tied to competencies. Each question uses retrieval for that competency.

    Args:
        db: AsyncSession
        document_id: Document UUID
        num_questions: Number of questions to generate
        role_profile: { domain, seniority, questionMix }
        competencies: List of { id, label, description?, evidence? }
        session_id: When set, loads ``InterviewSession.performance_profile``; if present,
            :func:`app.services.adaptive_engine.select_next_question_type` drives each
            question (otherwise question mix uses ``questionMix`` as before). Also loads the
            latest ``InterviewAnswer`` in that session so ``behavioral_followup`` can use
            strengths/gaps from the prior evaluation.

    Returns list of {
        id (placeholder, assigned by DB),
        type, competencyId, competencyLabel, questionText, whatGoodLooksLike,
        evidence, evidenceChunkIds
    }
    """
    rp = role_profile or DEFAULT_ROLE_PROFILE.copy()
    qmix = rp.get("questionMix") or DEFAULT_ROLE_PROFILE["questionMix"]
    b = int(qmix.get("behavioral", 40))
    r = int(qmix.get("roleSpecific", 30))
    s = int(qmix.get("scenario", 30))
    total = b + r + s
    if total != 100 and total > 0:
        b, r, s = round(100 * b / total), round(100 * r / total), round(100 * s / total)
        s = 100 - b - r
    type_cycle = []
    for _ in range(b):
        type_cycle.append("behavioral")
    for _ in range(r):
        type_cycle.append("role_specific")
    for _ in range(s):
        type_cycle.append("scenario")

    # Use focusAreas as pseudo-competencies if competencies empty
    comps = competencies
    if not comps:
        focus_areas = rp.get("focusAreas") or DEFAULT_ROLE_PROFILE["focusAreas"]
        comps = [{"id": f"fa-{i}", "label": str(fa)} for i, fa in enumerate(focus_areas[:num_questions])]
    if not comps:
        return []

    # Limit competencies to generate from
    comps = comps[: num_questions] if len(comps) > num_questions else comps
    results = []

    performance_profile_dict: dict | None = None
    last_answer_feedback: dict[str, list[str]] | None = None
    if session_id is not None:
        sess_row = await db.execute(select(InterviewSession).where(InterviewSession.id == session_id))
        sess_obj = sess_row.scalar_one_or_none()
        if sess_obj is not None:
            raw_profile = getattr(sess_obj, "performance_profile", None)
            if isinstance(raw_profile, dict) and raw_profile:
                performance_profile_dict = raw_profile

            ans_row = await db.execute(
                select(InterviewAnswer)
                .join(InterviewQuestion, InterviewAnswer.question_id == InterviewQuestion.id)
                .where(InterviewQuestion.session_id == session_id)
                .order_by(InterviewAnswer.created_at.desc())
                .limit(1)
            )
            last_ans = ans_row.scalar_one_or_none()
            if last_ans is not None:
                last_answer_feedback = _feedback_from_answer_row(last_ans)

    for i, comp in enumerate(comps):
        if len(results) >= num_questions:
            break
        comp_id = str(comp.get("id", f"comp-{i}"))
        comp_label = str(comp.get("label", "")).strip()
        if not comp_label:
            continue

        # Retrieve evidence for this competency
        evidence = await _retrieve_evidence_for_competency(db, document_id, comp_label)
        if not evidence:
            logger.info("No evidence for competency=%s, skipping", comp_label)
            continue

        adaptive_target: str | None = None
        if performance_profile_dict is not None:
            adaptive_target = select_next_question_type(performance_profile_dict)
            q_type = _ADAPTIVE_TO_CANONICAL_TYPE.get(adaptive_target)
            if not q_type:
                q_type = type_cycle[i % len(type_cycle)] if type_cycle else "behavioral"
                adaptive_target = None
        else:
            q_type = type_cycle[i % len(type_cycle)] if type_cycle else "behavioral"

        q = _generate_single_question(
            competency_id=comp_id,
            competency_label=comp_label,
            canonical_question_type=q_type,
            evidence=evidence,
            role_profile=rp,
            adaptive_target=adaptive_target,
            last_answer_feedback=last_answer_feedback,
        )
        if q and q.get("questionText"):
            results.append(q)

    return results[:num_questions]


def _build_domain_aware_prompt(
    role_profile: dict,
    evidence: list[dict],
    num_questions: int,
) -> tuple[str, str]:
    """Build system and user prompts for domain-aware question generation."""
    excerpt_lines = []
    for i, e in enumerate(evidence):
        snippet = normalize_jd_text(e.get("snippet", "")).strip()
        excerpt_lines.append(f"[{i}] {snippet}")

    excerpts_text = "\n\n".join(excerpt_lines)

    domain = role_profile.get("domain", "general_business")
    seniority = role_profile.get("seniority", "entry")
    focus_areas = role_profile.get("focusAreas") or []
    question_mix = role_profile.get("questionMix") or {}

    b = int(question_mix.get("behavioral", 40))
    r = int(question_mix.get("roleSpecific", 30))
    s = int(question_mix.get("scenario", 30))
    total = b + r + s
    if total != 100 and total > 0:
        b, r, s = round(100 * b / total), round(100 * r / total), round(100 * s / total)
        s = 100 - b - r

    role_specific_hint = DOMAIN_ROLE_SPECIFIC_GUIDANCE.get(domain, DOMAIN_ROLE_SPECIFIC_GUIDANCE["general_business"])
    seniority_hint = "entry-level" if seniority == "entry" else "mid-level" if seniority == "mid" else "senior-level"

    focus_areas_text = ", ".join(focus_areas) if focus_areas else "communication, problem solving"

    system_prompt = f"""You are an expert hiring manager creating interview questions from a job description.
Generate questions that are DOMAIN-AWARE and tailored to the role.

DOMAIN: {domain}
SENIORITY: {seniority} ({seniority_hint})
FOCUS AREAS (each question must map to ONE): {focus_areas_text}

QUESTION TYPES:
- behavioral: Past experience, STAR format, "Tell me about a time..."
- role_specific: Domain knowledge for this role. For {domain}, cover: {role_specific_hint}
- scenario: Hypothetical "What would you do if..." situations

QUESTION MIX (approximate): behavioral {b}%, role_specific {r}%, scenario {s}%

RULES:
1. Each question MUST map to exactly one focusArea from the list above.
2. Scale depth and difficulty by seniority ({seniority_hint}).
3. Ground questions in the evidence excerpts; cite by index [0], [1], etc. in evidence_indices.
4. whatGoodLooksLike: 2-4 bullets describing what a strong answer covers.
5. mustMention: 0-3 bullets of key points the answer should reference (optional, can be empty).

Output valid JSON only, no markdown:
{{"questions": [{{"type": "behavioral"|"role_specific"|"scenario", "focusArea": "...", "question": "...", "whatGoodLooksLike": ["...","..."], "mustMention": ["..."]|[], "evidence_indices": [0,1]}}]}}"""

    user_content = f"""Job description excerpts (each prefixed with index):
{excerpts_text}

Generate exactly {num_questions} questions. Follow the question mix and map each to a focus area.
Output JSON only."""

    return system_prompt, user_content


def _parse_domain_aware_questions(raw: str, evidence: list[dict]) -> list[dict]:
    """Parse LLM JSON output into structured questions."""
    text = raw.strip()
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        text = json_match.group(0)

    data = json.loads(text)
    questions = data.get("questions", [])
    result = []

    def _to_str_list(v) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if x]

    for q in questions:
        qtype = str(q.get("type", "")).strip().lower()
        if qtype not in VALID_QUESTION_TYPES:
            qtype = "behavioral"

        idx_list = q.get("evidence_indices") or []
        if not isinstance(idx_list, list):
            idx_list = []
        evidence_for_q = []
        for idx in idx_list:
            if isinstance(idx, int) and 0 <= idx < len(evidence):
                evidence_for_q.append(evidence[idx])
        if not evidence_for_q and evidence:
            evidence_for_q = evidence[:3]

        what_good = _to_str_list(q.get("whatGoodLooksLike") or q.get("rubric") or [])
        must_mention = _to_str_list(q.get("mustMention") or [])
        focus_area = str(q.get("focusArea") or "").strip()

        result.append({
            "type": qtype,
            "focusArea": focus_area,
            "question": str(q.get("question", "")).strip(),
            "whatGoodLooksLike": what_good,
            "mustMention": must_mention,
            "evidence": evidence_for_q,
        })

    return result


def generate_interview_questions(
    role_profile: dict,
    retrieved_evidence_chunks: list[dict],
    num_questions: int,
) -> list[dict]:
    """
    Generate interview questions using roleProfile (domain-aware).

    Args:
        role_profile: { domain, seniority, focusAreas, questionMix }
        retrieved_evidence_chunks: list of {chunk_id, page_number, snippet}
        num_questions: number of questions to generate

    Returns list of {
        type: "behavioral"|"role_specific"|"scenario",
        focusArea: str,
        question: str,
        whatGoodLooksLike: list[str],
        mustMention: list[str],
        evidence: list[dict]
    }
    """
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    rp = role_profile or DEFAULT_ROLE_PROFILE.copy()
    system_prompt, user_content = _build_domain_aware_prompt(rp, retrieved_evidence_chunks, num_questions)

    # Batch question generation uses MODEL_FAST only (not MODEL_HIGH_QUALITY).
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.model_fast,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=min(2000, settings.max_completion_tokens * 4),  # need more for structured JSON
    )

    raw = (response.choices[0].message.content or "").strip()
    return _parse_domain_aware_questions(raw, retrieved_evidence_chunks)
