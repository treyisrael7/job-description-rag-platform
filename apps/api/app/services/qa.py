"""Grounded Q&A over uploaded document excerpts."""

import json
import logging
import re
from openai import OpenAI

from app.core.config import settings
from app.services.jd_sections import normalize_jd_text
from app.services.token_budget import budget_grounded_qa_prompt

logger = logging.getLogger(__name__)

# OpenAI sampling: keep deterministic, within 0-0.3 per product guidance.
QA_TEMPERATURE = 0.2

_SYSTEM_PROMPT = """You answer questions about an uploaded job description PDF using retrieved excerpts.

You are given:
1. Job description/document excerpts
2. Optional candidate resume excerpts

Tasks:
- Answer the user's question directly and concisely.
- Use only facts present in the excerpts.
- Cite factual claims with the exact citation labels supplied in the excerpts, such as [p2-c3].
- If the excerpts do not contain the answer, say you could not find that information in the uploaded document.
- If the user asks about candidate fit and resume excerpts are available, compare the JD and resume using only the excerpts and cite both where relevant.

Do not invent details. Do not return JSON. Do not use markdown tables."""

_ANSWER_INSTRUCTIONS = """
Write a concise answer in plain text.
Include citation labels inline immediately after the sentence or phrase they support, using exactly the labels shown above, for example [p1-c2].
If multiple excerpts support a sentence, include multiple labels.
"""


def _split_jd_resume_chunks(chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    jd: list[dict] = []
    resume: list[dict] = []
    for c in chunks:
        st = str(c.get("source_type") or "").strip().upper()
        if st == "RESUME":
            resume.append(c)
        else:
            jd.append(c)
    return jd, resume


def _format_excerpt_block(label: str, chunks: list[dict], start_index: int) -> tuple[str, int]:
    """Build labeled excerpt lines with [p{page}-c{i}] markers; returns (text, next_index)."""
    lines: list[str] = []
    i = start_index
    for c in chunks:
        marker = f"[{_citation_label(c, i)}]"
        snippet = normalize_jd_text(c.get("snippet", "")).strip()
        lines.append(f"{marker} {snippet}")
        i += 1
    body = "\n\n".join(lines) if lines else "(No excerpt text in this section.)"
    return f"### {label}\n{body}", i


def _build_user_content_for_budget(jd_chunks: list[dict], resume_chunks: list[dict], question: str) -> str:
    jd_block, next_idx = _format_excerpt_block("Job description excerpts", jd_chunks, start_index=1)
    resume_block, _ = _format_excerpt_block(
        "Candidate resume excerpts", resume_chunks, start_index=next_idx
    )
    return f"""{jd_block}

{resume_block}

User question / focus:
{question.strip()}

{_ANSWER_INSTRUCTIONS.strip()}
"""


def _extract_json_object(raw: str) -> str:
    raw = (raw or "").strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    return m.group(0) if m else raw


def _citation_label(chunk: dict, index: int) -> str:
    page = chunk.get("page_number") if chunk.get("page_number") is not None else chunk.get("page")
    try:
        page_num = int(page)
    except (TypeError, ValueError):
        page_num = 0
    return f"p{page_num}-c{index}"


# Chunks are list of {chunk_id, page_number, snippet, source_type?, ...}
# Returns (answer_json_string, citations)
def generate_grounded_answer(
    question: str,
    chunks: list[dict],
    max_tokens: int | None = None,
) -> tuple[str, list[dict]]:
    """
    Call OpenAI with grounded document QA instructions. Citations mirror the
    excerpts that were supplied to the model and include the labels shown there.
    """
    max_tokens = max_tokens or settings.max_completion_tokens
    max_tokens = max(max_tokens, 1200)

    if not chunks:
        return (
            "We could not find enough relevant text in the uploaded document to answer that. Try asking in a different way.",
            [],
        )

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    budget_chunks, user_content, effective_max_tokens = budget_grounded_qa_prompt(
        question=question,
        chunks=chunks,
        system_prompt=_SYSTEM_PROMPT,
        split_chunks=_split_jd_resume_chunks,
        build_user_content=lambda jd_c, rs_c: _build_user_content_for_budget(jd_c, rs_c, question),
        requested_completion_tokens=max_tokens,
        total_budget=settings.max_llm_budget_tokens,
    )

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.model_fast,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=effective_max_tokens,
        temperature=QA_TEMPERATURE,
    )

    answer = (response.choices[0].message.content or "").strip()
    if not answer:
        answer = "We could not find enough relevant text in the uploaded document to answer that."

    citations = [
        {
            "label": _citation_label(c, i),
            "chunk_id": str(c.get("chunk_id") or c.get("chunkId") or ""),
            "page_number": int(c.get("page_number") if c.get("page_number") is not None else c.get("page") or 0),
            "snippet": normalize_jd_text(c.get("snippet", "")),
        }
        for i, c in enumerate(budget_chunks, start=1)
    ]

    return answer, citations


# --- Profile resume coaching ---

_RESUME_COACH_SYSTEM = """You are a friendly, practical resume coach talking to one person.

You only see excerpts from their resume.

How to help:
- Answer their question using only what appears in the resume excerpts.
- Give concrete, doable advice: clearer wording, stronger bullets, better structure, what to trim, ATS-friendly phrasing when it helps.
- Offer specific rewrite ideas and bullet patterns instead of generic praise.
- If the excerpts are too thin to answer, say so briefly in coaching_reply and suggest what they could add to the resume.
- Never invent employers, degrees, tools, or numbers that are not supported by the excerpts.

Return STRICT JSON only."""

_RESUME_COACH_JSON = """
Return one JSON object with exactly these keys (no markdown, no code fences, no extra keys):
- "coaching_reply": string (direct answer to the user's question)
- "prioritized_edits": array of objects, each with "focus" (string), "observation" (string), "suggestion" (string). Use [] if none apply.
- "strengths_to_keep": array of strings (what is already working on the resume). Use [] if none.
- "reasoning": string (short note tying your advice to specific phrases or sections visible in the excerpts)
"""


def _split_all_chunks_as_resume(chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Primary resume-doc chunks may be labeled JD internally; treat all as resume for coaching."""
    return [], [{**c} for c in chunks]


def _build_resume_coach_user_content(
    _jd_chunks: list[dict],
    resume_chunks: list[dict],
    question: str,
) -> str:
    resume_block, _ = _format_excerpt_block("Resume excerpts", resume_chunks, start_index=1)
    return f"""{resume_block}

User question:
{question.strip()}

{_RESUME_COACH_JSON.strip()}
"""


def generate_resume_improvement_answer(
    question: str,
    chunks: list[dict],
    max_tokens: int | None = None,
) -> tuple[str, list[dict]]:
    """
    Grounded resume coaching. ``answer`` is a JSON string; citations mirror chunks used.
    """
    max_tokens = max_tokens or settings.max_completion_tokens
    max_tokens = max(max_tokens, 1200)

    if not chunks:
        return (
            "We could not pull enough text from your resume to answer that. Try a broader question or re-upload your PDF if something looks wrong.",
            [],
        )

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    budget_chunks, user_content, effective_max_tokens = budget_grounded_qa_prompt(
        question=question,
        chunks=chunks,
        system_prompt=_RESUME_COACH_SYSTEM,
        split_chunks=_split_all_chunks_as_resume,
        build_user_content=lambda jd_c, rs_c: _build_resume_coach_user_content(jd_c, rs_c, question),
        requested_completion_tokens=max_tokens,
        total_budget=settings.max_llm_budget_tokens,
    )

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.model_fast,
        messages=[
            {"role": "system", "content": _RESUME_COACH_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        max_tokens=effective_max_tokens,
        temperature=QA_TEMPERATURE,
        response_format={"type": "json_object"},
    )

    raw = (response.choices[0].message.content or "").strip()
    answer: str
    try:
        payload = json.loads(_extract_json_object(raw))
        if not isinstance(payload, dict):
            raise TypeError("root must be object")
        answer = json.dumps(payload, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning("Resume coach JSON parse failed, returning raw model text: %s", e)
        answer = raw

    citations = [
        {
            "chunk_id": str(c.get("chunk_id") or c.get("chunkId") or ""),
            "page_number": int(c.get("page_number") if c.get("page_number") is not None else c.get("page") or 0),
            "snippet": normalize_jd_text(c.get("snippet", "")),
        }
        for c in budget_chunks
    ]

    return answer, citations
