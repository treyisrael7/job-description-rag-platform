"""Answer evaluation: prompts, parsing, validation, and retrieval-backed scoring."""

import asyncio
import copy
import difflib
import json
import logging
import re
import uuid

try:
    from json_repair import loads as json_repair_loads
except ImportError:
    json_repair_loads = None  # type: ignore[misc, assignment]

from openai import OpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.llm_cache import (
    cache_get_json,
    cache_set_json,
    evaluation_cache_key,
    retrieval_cache_key,
)
from app.models import Document, InterviewSource
from app.services.interview.constants import (
    AUXILIARY_SOURCE_TYPES,
    COMPETENCY_EVIDENCE_TOP_K,
    DEFAULT_ROLE_PROFILE,
    EVALUATION_DOMAIN_HINTS,
    EVALUATION_QUERY_TOP_K,
    EVALUATION_SYSTEM_PROMPT,
    EVALUATION_SYSTEM_PROMPT_LITE,
)
from app.services.interview.evidence import (
    _get_or_create_session_jd_pool,
    _rank_pool_for_query,
    _retrieve_evidence_for_competency,
    _retrieval_dict_to_evidence_item,
    get_user_resume_document_id,
    normalize_evaluation_evidence,
)
from app.services.retrieval import embed_query, retrieve_chunks

logger = logging.getLogger(__name__)

def _evaluation_system_prompt_for_mode(evaluation_mode: str) -> str:
    m = (evaluation_mode or "full").strip().lower()
    if m == "lite":
        return EVALUATION_SYSTEM_PROMPT_LITE
    return EVALUATION_SYSTEM_PROMPT


def _format_document_rubric_block(document_rubric_json: list[dict] | None) -> str:
    """Human- and model-readable block for JD-level evaluation dimensions (name + description)."""
    if not document_rubric_json:
        return ""
    payload: list[dict[str, str]] = []
    for d in document_rubric_json:
        if not isinstance(d, dict):
            continue
        name = str(d.get("name", "")).strip()
        if not name:
            continue
        payload.append(
            {
                "name": name,
                "description": str(d.get("description", "")).strip(),
            }
        )
    if not payload:
        return ""
    rubric_json = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "## Role-specific dimensions\n\n"
        "You must evaluate the candidate based on the following role-specific dimensions:\n\n"
        f"{rubric_json}\n\n"
        "For each dimension:\n"
        "- assign a score (0–10)\n"
        "- explain reasoning\n\n"
        "Then compute an overall score based on these dimensions "
        "(the JSON field `score` must equal the unweighted mean of those per-dimension scores).\n\n"
    )


def _build_domain_aware_evaluation_prompt(
    question: str,
    question_type: str,
    focus_area: str,
    competency_label: str | None,
    what_good_looks_like: list[str],
    must_mention: list[str],
    evidence: list[dict],
    role_profile: dict,
    answer_text: str,
    document_rubric_json: list[dict] | None = None,
    evaluation_mode: str = "full",
) -> tuple[str, str]:
    """Build prompts: system message (full vs lite) + user message with Q, rubric, chunks, answer."""
    rubric_lines = [f"• {b}" for b in (what_good_looks_like or []) if str(b).strip()]
    if must_mention:
        rubric_lines.append("Must mention: " + "; ".join(must_mention))
    rubric_text = "\n".join(rubric_lines) if rubric_lines else "(No separate rubric bullets; rely on job description chunks.)"

    evidence_lines = []
    for i, e in enumerate(evidence or []):
        s = (e.get("text") or e.get("snippet") or "").strip()
        cid = e.get("chunk_id") or e.get("chunkId") or ""
        pg = e.get("page_number") if e.get("page_number") is not None else e.get("page")
        try:
            pnv = int(pg) if pg is not None else 0
        except (TypeError, ValueError):
            pnv = 0
        sec = e.get("section_type")
        section_type = str(sec).strip() if sec not in (None, "") else "general"
        src_type = e.get("sourceType", "jd")
        src_title = e.get("sourceTitle", "")
        if s:
            meta = (
                f"[{i}] chunk_id={cid} section_type={section_type} "
                f"sourceType={src_type} sourceTitle={src_title} page_number={pnv}"
            )
            evidence_lines.append(f"{meta}\n{s[:500]}")
    evidence_text = "\n\n".join(evidence_lines) if evidence_lines else "(No job description chunks provided.)"

    domain = role_profile.get("domain", "general_business")
    seniority = role_profile.get("seniority", "entry")
    interview_difficulty = str(role_profile.get("interviewDifficulty") or "mid").strip().lower()
    difficulty_hint = {
        "junior": "Expect fundamentals, clear communication, and credible baseline examples; do not penalize for missing senior-level architecture unless the rubric explicitly requires it.",
        "mid": "Expect independent delivery, practical tradeoffs, debugging, and collaboration depth.",
        "senior": "Expect ambiguity handling, strategy, tradeoffs, leadership, mentoring, and measurable impact.",
    }.get(interview_difficulty, "Expect realistic mid-level depth.")
    domain_hint = EVALUATION_DOMAIN_HINTS.get(domain, EVALUATION_DOMAIN_HINTS["general_business"])

    header = f"""Session context (use when tuning expectations):
- Question type: {question_type}
- Focus area: {focus_area}
- Competency: {competency_label or "(none)"}
- Role domain: {domain} | Seniority: {seniority}
- Interview difficulty: {interview_difficulty}
- Difficulty expectation: {difficulty_hint}
- Domain note: {domain_hint}

"""

    doc_rubric_block = _format_document_rubric_block(document_rubric_json)

    user_content = f"""{header}## Interview question
{question}

{doc_rubric_block}## Rubric and expected skills (from role / question setup)
{rubric_text}

## Retrieved job description chunks (only valid sources for "citations"; cite these chunk_id values exactly)
{evidence_text}

## Candidate's answer (quote from this text in strengths' evidence where applicable)
{answer_text}
"""

    return _evaluation_system_prompt_for_mode(evaluation_mode), user_content


def _citation_from_evidence(e: dict) -> dict:
    """Build {chunkId, page?, sourceTitle, sourceType} from evidence item."""
    chunk_id = str(e.get("chunk_id") or e.get("chunkId") or "")
    page = e.get("page_number") or e.get("page")
    return {
        "chunkId": chunk_id,
        "page": int(page) if page is not None else None,
        "sourceTitle": str(e.get("sourceTitle", "")),
        "sourceType": str(e.get("sourceType", "jd")),
    }


def _citation_row_from_evidence_index(ev: list[dict], idx: int) -> dict | None:
    """Build {chunk_id, page_number, text} from evidence list index."""
    if not isinstance(idx, int) or idx < 0 or idx >= len(ev):
        return None
    e = ev[idx]
    chunk_id = str(e.get("chunk_id") or e.get("chunkId") or "")
    pg = e.get("page_number") or e.get("page")
    try:
        page_number = int(pg) if pg is not None else 0
    except (TypeError, ValueError):
        page_number = 0
    body = str(e.get("text") or e.get("snippet") or "").strip()
    return {
        "chunk_id": chunk_id,
        "page_number": page_number,
        "text": body[:800],
    }


def _strip_json_markdown_fence(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_first_balanced_json_object(s: str) -> str | None:
    """First top-level `{...}` with string-aware brace matching (avoids greedy-regex mistakes)."""
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    i = start
    n = len(s)
    in_string = False
    escape = False
    while i < n:
        c = s[i]
        if escape:
            escape = False
            i += 1
            continue
        if in_string:
            if c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
        i += 1
    return None


def _remove_trailing_commas_json(s: str) -> str:
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r",(\s*[}\]])", r"\1", s)
    return s


def _loads_evaluation_json(raw: str) -> dict:
    """
    Parse model evaluation JSON: strip fences, extract balanced object, then strict parse,
    trailing-comma fix, or json_repair fallback.
    """
    text = _strip_json_markdown_fence(raw)
    extracted = _extract_first_balanced_json_object(text)
    if extracted:
        text = extracted
    text = text.strip()
    last_err: Exception | None = None
    candidates = [text, _remove_trailing_commas_json(text)]
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
            last_err = ValueError(f"Expected JSON object, got {type(data).__name__}")
        except json.JSONDecodeError as e:
            last_err = e
        if json_repair_loads is not None:
            try:
                data = json_repair_loads(candidate)
                if isinstance(data, dict):
                    return data
                last_err = ValueError(f"Expected JSON object, got {type(data).__name__}")
            except Exception as e:  # noqa: BLE001 — lenient parser may raise varied errors
                last_err = e
    if last_err is not None:
        raise last_err
    raise json.JSONDecodeError("Expected JSON object", text, 0)


def _fallback_evaluation_parse(evidence: list[dict]) -> dict:
    """Minimal valid shape when the model output is not parseable JSON."""
    return {
        "score": 5.0,
        "summary": (
            "The automated evaluation response could not be read (invalid or truncated JSON). "
            "Your answer was saved. Try submitting again, or use a slightly shorter answer if the issue persists."
        ),
        "strengths": [],
        "gaps": [],
        "citations": [],
        "strengths_cited": [],
        "gaps_cited": [],
        "improved_answer": "",
        "follow_up_questions": [],
        "suggested_followup": None,
        "evidence_used": [],
        "score_reasoning": "",
        "rubric_scores": [],
        "_llm_citation_entries": 0,
    }


def _normalize_rubric_scores_list(raw: list | None) -> list[dict[str, float | str]]:
    """
    Canonical rubric_scores: name (str), score (float 0–10 per dimension), reasoning (explains that score).

    Empty or missing reasoning is replaced so downstream consumers always get an explanatory string.
    """
    out: list[dict[str, float | str]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        rs = item.get("score")
        try:
            score_f = max(0.0, min(10.0, float(rs)))
        except (TypeError, ValueError):
            score_f = 0.0
        reasoning = str(item.get("reasoning", "")).strip()
        if not reasoning:
            reasoning = (
                f"Assigned {score_f:.1f}/10 for this dimension: the answer's fit to «{name}» "
                "given the question, rubric, and job description context."
            )
        out.append({"name": name, "score": score_f, "reasoning": reasoning})
    return out


# Public alias for routers/tests that need the same canonical shape.
normalize_rubric_scores_output = _normalize_rubric_scores_list


def _dedupe_citations(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        cid = str(r.get("chunk_id", ""))
        if not cid:
            continue
        if cid in seen:
            continue
        seen.add(cid)
        out.append(
            {
                "chunk_id": cid,
                "page_number": int(r.get("page_number", 0) or 0),
                "text": str(r.get("text", "")),
            }
        )
    return out


def _parse_evaluation_response(raw: str, evidence: list[dict]) -> dict:
    """
    Parse LLM evaluation JSON.

    Returns score (0-10), summary, score_reasoning, strengths [{text, evidence, highlight, impact}],
    gaps [{text, missing, expected, jd_alignment, improvement}], citations [{chunk_id, page_number, text}],
    strengths_cited/gaps_cited for API compatibility, evidence_used, and follow-up fields.
    """
    try:
        data = _loads_evaluation_json(raw)
    except Exception as e:
        logger.warning(
            "evaluation JSON parse failed: %s; raw_snippet=%r",
            e,
            (raw or "")[:1500],
        )
        return _fallback_evaluation_parse(evidence)

    def _indices_for(item: dict) -> list[int]:
        idx_list = item.get("citation_indices")
        if not isinstance(idx_list, list):
            return []
        out: list[int] = []
        for idx in idx_list:
            if isinstance(idx, int) and 0 <= idx < len(evidence):
                out.append(idx)
        return out

    def _parse_cited_strengths_gaps(
        raw_strengths: list[dict] | list[str],
        raw_gaps: list[dict] | list[str],
    ) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
        """Return strengths_out, gaps_out, strengths_cited, gaps_cited."""
        s_list = raw_strengths if isinstance(raw_strengths, list) else []
        g_list = raw_gaps if isinstance(raw_gaps, list) else []
        if s_list and isinstance(s_list[0], str):
            s_list = [
                {"text": s, "evidence": "", "citation_indices": [], "highlight": "", "impact": ""}
                for s in s_list
            ]
        if g_list and isinstance(g_list[0], str):
            g_list = [
                {
                    "text": g,
                    "missing": "",
                    "expected": "",
                    "jd_alignment": "",
                    "improvement": "",
                    "citation_indices": [],
                }
                for g in g_list
            ]

        strengths_out: list[dict] = []
        gaps_out: list[dict] = []
        strengths_cited: list[dict] = []
        gaps_cited: list[dict] = []

        for item in s_list:
            if not isinstance(item, dict):
                continue
            t = str(item.get("text", "")).strip()
            ev_txt = str(item.get("evidence", "")).strip()
            if not ev_txt and isinstance(item.get("citation_indices"), list):
                # Legacy: only indices, no evidence string
                parts = []
                for idx in _indices_for(item):
                    row = _citation_row_from_evidence_index(evidence, idx)
                    if row:
                        parts.append(row["text"])
                ev_txt = "; ".join(parts) if parts else "JD does not specify"
            hl_raw = str(item.get("highlight", "")).strip()
            impact = str(item.get("impact", "")).strip()
            strengths_out.append(
                {
                    "text": t,
                    "evidence": ev_txt or "JD does not specify",
                    "highlight": hl_raw,
                    "impact": impact,
                }
            )
            idx_list = item.get("citation_indices")
            if not isinstance(idx_list, list):
                idx_list = []
            citations = []
            for idx in idx_list:
                if isinstance(idx, int) and 0 <= idx < len(evidence):
                    citations.append(_citation_from_evidence(evidence[idx]))
            strengths_cited.append({"text": t, "citations": citations})

        for item in g_list:
            if not isinstance(item, dict):
                continue
            t = str(item.get("text", "")).strip()
            missing = str(item.get("missing", "")).strip()
            exp = str(item.get("expected", "")).strip()
            jd_alignment = str(item.get("jd_alignment", "")).strip()
            improvement = str(item.get("improvement", "")).strip()
            if not exp:
                exp = "Align with rubric and JD evidence."
            gaps_out.append(
                {
                    "text": t,
                    "missing": missing,
                    "expected": exp,
                    "jd_alignment": jd_alignment,
                    "improvement": improvement,
                }
            )
            idx_list = item.get("citation_indices")
            if not isinstance(idx_list, list):
                idx_list = []
            citations = []
            for idx in idx_list:
                if isinstance(idx, int) and 0 <= idx < len(evidence):
                    citations.append(_citation_from_evidence(evidence[idx]))
            gaps_cited.append({"text": t, "citations": citations})

        return strengths_out, gaps_out, strengths_cited, gaps_cited

    raw_strengths = data.get("strengths") or []
    raw_gaps = data.get("gaps") or []
    strengths, gaps, strengths_cited, gaps_cited = _parse_cited_strengths_gaps(raw_strengths, raw_gaps)

    # Top-level citations: LLM optional list + union of all cited indices
    citation_rows: list[dict] = []
    raw_citations = data.get("citations")
    if isinstance(raw_citations, list):
        for c in raw_citations:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("chunk_id") or c.get("chunkId") or "")
            if not cid:
                continue
            allowed = {str(e.get("chunk_id") or e.get("chunkId", "")) for e in evidence}
            if cid not in allowed:
                continue
            pg = c.get("page_number") if c.get("page_number") is not None else c.get("page")
            try:
                pn = int(pg) if pg is not None else 0
            except (TypeError, ValueError):
                pn = 0
            citation_rows.append(
                {
                    "chunk_id": cid,
                    "page_number": pn,
                    "text": str(c.get("text", "")).strip()[:800],
                }
            )

    for coll in (raw_strengths, raw_gaps):
        if not isinstance(coll, list):
            continue
        for item in coll:
            if not isinstance(item, dict):
                continue
            for idx in item.get("citation_indices") or []:
                if isinstance(idx, int):
                    row = _citation_row_from_evidence_index(evidence, idx)
                    if row:
                        citation_rows.append(row)

    citations = _dedupe_citations(citation_rows)

    # evidence_used for Reference / legacy API (same shape as before)
    seen_ids: set[str] = set()
    evidence_used: list[dict] = []
    for row in citations:
        cid = row["chunk_id"]
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        for e in evidence:
            if str(e.get("chunk_id") or e.get("chunkId", "")) == cid:
                pg = row.get("page_number")
                evidence_used.append(
                    {
                        "quote": str(e.get("text") or e.get("snippet") or "").strip()[:400],
                        "sourceId": cid,
                        "sourceType": str(e.get("sourceType", "jd")),
                        "sourceTitle": str(e.get("sourceTitle", "")),
                        "page": pg,
                        "chunkId": cid,
                    }
                )
                break

    score = data.get("score")
    if score is not None:
        try:
            score = max(0, min(10, float(score)))
        except (TypeError, ValueError):
            score = 5.0
    else:
        score = 5.0

    sug = data.get("suggested_followup")
    follow_up = [str(sug).strip()] if sug else []

    summary = str(data.get("summary") or "").strip()
    score_reasoning = str(data.get("score_reasoning") or "").strip()

    rubric_scores = _normalize_rubric_scores_list(data.get("rubric_scores"))

    raw_cit_list = data.get("citations")
    llm_citation_entries = len(
        [x for x in (raw_cit_list if isinstance(raw_cit_list, list) else []) if isinstance(x, dict)]
    )

    return {
        "score": score,
        "summary": summary,
        "score_reasoning": score_reasoning,
        "strengths": strengths,
        "gaps": gaps,
        "citations": citations,
        "strengths_cited": strengths_cited,
        "gaps_cited": gaps_cited,
        "improved_answer": str(data.get("improved_answer") or "").strip(),
        "follow_up_questions": follow_up,
        "suggested_followup": str(sug).strip() if sug else None,
        "evidence_used": evidence_used,
        "rubric_scores": rubric_scores,
        "_llm_citation_entries": llm_citation_entries,
    }


def _chunk_id_map(retrieved_chunks: list[dict]) -> dict[str, dict]:
    """chunk_id -> chunk dict."""
    m: dict[str, dict] = {}
    for e in retrieved_chunks or []:
        if not isinstance(e, dict):
            continue
        cid = str(e.get("chunk_id") or e.get("chunkId") or "").strip()
        if cid:
            m[cid] = e
    return m


def _evidence_used_from_citations(
    citations: list[dict],
    retrieved_chunks: list[dict],
) -> list[dict]:
    """Rebuild evidence_used from validated citations and stored chunk text."""
    chunk_map = _chunk_id_map(retrieved_chunks)
    seen: set[str] = set()
    out: list[dict] = []
    for row in citations or []:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("chunk_id") or "").strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)
        e = chunk_map.get(cid)
        quote = str(row.get("text") or "").strip()
        if e is not None:
            if not quote:
                quote = str(e.get("text") or e.get("snippet") or "").strip()[:400]
            pg = row.get("page_number")
            try:
                page = int(pg) if pg is not None else int(e.get("page_number") or 0)
            except (TypeError, ValueError):
                page = int(e.get("page_number") or 0)
            out.append(
                {
                    "quote": quote[:400],
                    "sourceId": cid,
                    "sourceType": str(e.get("sourceType", "jd")),
                    "sourceTitle": str(e.get("sourceTitle", "")),
                    "page": page,
                    "chunkId": cid,
                }
            )
        else:
            try:
                pn = int(row.get("page_number") or 0)
            except (TypeError, ValueError):
                pn = 0
            out.append(
                {
                    "quote": quote[:400],
                    "sourceId": cid,
                    "sourceType": "jd",
                    "sourceTitle": "",
                    "page": pn,
                    "chunkId": cid,
                }
            )
    return out


def _find_verbatim_span_in_answer(user_answer: str, candidate: str) -> str:
    """Return the substring of user_answer that matches candidate (case-insensitive), or ""."""
    if not user_answer or not candidate or not candidate.strip():
        return ""
    ua = user_answer
    cand = candidate.strip()
    try:
        m = re.search(re.escape(cand), ua, flags=re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(0)
    except re.error:
        pass
    lo, cl = ua.lower(), cand.lower()
    i = lo.find(cl)
    if i >= 0:
        return ua[i : i + len(cand)]
    return ""


def _longest_common_substring_span(a: str, b: str, min_len: int) -> tuple[str, int, int] | None:
    """Return (substring_of_a, start_in_a, len) for longest common contiguous match between a and b."""
    if not a or not b:
        return None
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    m = sm.find_longest_match(0, len(a), 0, len(b))
    if m.size < min_len:
        return None
    return (a[m.a : m.a + m.size], m.a, m.size)


def enrich_strength_highlights(strengths: list[dict], user_answer: str) -> list[dict]:
    """
    Ensure each strength has a ``highlight`` that is an exact phrase from ``user_answer``
    (LLM value validated, else substring / fuzzy match from evidence or text).
    """
    ua = (user_answer or "").strip()
    out: list[dict] = []
    for s in strengths or []:
        if not isinstance(s, dict):
            continue
        ns = dict(s)
        ev = str(ns.get("evidence", "")).strip()
        tx = str(ns.get("text", "")).strip()
        hl_in = str(ns.get("highlight", "")).strip()

        resolved = ""
        if ua:
            resolved = _find_verbatim_span_in_answer(ua, hl_in)
            if not resolved and ev:
                resolved = _find_verbatim_span_in_answer(ua, ev)
            if not resolved and ev and len(ev) >= 4:
                lcs = _longest_common_substring_span(ua, ev, 5)
                if lcs:
                    resolved = lcs[0]
            if not resolved and tx and len(tx) >= 6:
                lcs = _longest_common_substring_span(ua, tx, 8)
                if lcs:
                    resolved = lcs[0]
            if not resolved and ev:
                # Sentence-level: best ratio between answer sentences and evidence
                best = ""
                best_r = 0.0
                for sent in re.split(r"(?<=[.!?])\s+|\n+", ua):
                    snt = sent.strip()
                    if len(snt) < 12:
                        continue
                    r = difflib.SequenceMatcher(None, snt.lower(), ev.lower()).ratio()
                    if r > best_r and r >= 0.42:
                        best_r = r
                        best = snt
                if best and len(best) <= 400:
                    resolved = best

        ns["highlight"] = (resolved or "")[:400]
        out.append(ns)
    return out


def _filter_citation_dict(cit: dict, allowed: set[str]) -> bool:
    ck = str(cit.get("chunkId") or cit.get("chunk_id") or "").strip()
    return ck in allowed


def validate_evaluation_output(
    response: dict,
    retrieved_chunks: list[dict],
    evaluation_mode: str = "full",
) -> dict:
    """
    Post-LLM validation: drop citations whose chunk_id is not in retrieved chunks;
    rebuild evidence_used; prune invalid nested citations; ensure non-empty strengths/gaps (full only).
    """
    out = dict(response)
    mode = (evaluation_mode or "full").strip().lower()
    if mode == "lite":
        out["citations"] = []
        out["evidence_used"] = []
        out["improved_answer"] = ""
        out["strengths"] = []
        out["gaps"] = []
        out["strengths_cited"] = []
        out["gaps_cited"] = []
        out["score_reasoning"] = str(out.get("score_reasoning") or "").strip()
        out["rubric_scores"] = _normalize_rubric_scores_list(out.get("rubric_scores"))
        return out
    allowed = {
        str(e.get("chunk_id") or e.get("chunkId") or "").strip()
        for e in (retrieved_chunks or [])
        if isinstance(e, dict) and (e.get("chunk_id") or e.get("chunkId"))
    }
    chunk_map = _chunk_id_map(retrieved_chunks)

    # --- Citations: keep only chunk_ids present in retrieved context ---
    filtered_citations: list[dict] = []
    for c in list(out.get("citations") or []):
        if not isinstance(c, dict):
            continue
        cid = str(c.get("chunk_id") or c.get("chunkId") or "").strip()
        if cid not in allowed:
            continue
        src = chunk_map.get(cid, {})
        pg = c.get("page_number") if c.get("page_number") is not None else c.get("page")
        try:
            pn = int(pg) if pg is not None else int(src.get("page_number") or 0)
        except (TypeError, ValueError):
            pn = int(src.get("page_number") or 0)
        txt = str(c.get("text") or "").strip()
        if not txt:
            txt = str(src.get("text") or src.get("snippet") or "").strip()[:800]
        filtered_citations.append({"chunk_id": cid, "page_number": pn, "text": txt})
    out["citations"] = _dedupe_citations(filtered_citations)
    out["evidence_used"] = _evidence_used_from_citations(out["citations"], retrieved_chunks)

    # --- Strengths / gaps: drop empty dicts; require at least one item each ---
    strengths: list[dict] = []
    for s in list(out.get("strengths") or []):
        if not isinstance(s, dict):
            continue
        t = str(s.get("text", "")).strip()
        if not t:
            continue
        ev = str(s.get("evidence", "")).strip()
        hl = str(s.get("highlight", "")).strip()
        impact = str(s.get("impact", "")).strip()
        strengths.append(
            {
                "text": t,
                "evidence": ev or "See answer and rubric context.",
                "highlight": hl,
                "impact": impact,
            }
        )

    gaps: list[dict] = []
    for g in list(out.get("gaps") or []):
        if not isinstance(g, dict):
            continue
        t = str(g.get("text", "")).strip()
        if not t:
            continue
        missing = str(g.get("missing", "")).strip()
        exp = str(g.get("expected", "")).strip()
        jd_alignment = str(g.get("jd_alignment", "")).strip()
        improvement = str(g.get("improvement", "")).strip()
        gaps.append(
            {
                "text": t,
                "missing": missing,
                "expected": exp or "Align with rubric and job description context.",
                "jd_alignment": jd_alignment,
                "improvement": improvement,
            }
        )

    if not strengths:
        strengths = [
            {
                "text": "No specific strengths were identified in this evaluation pass.",
                "evidence": "The model did not return quotable strengths; compare your answer to the rubric and job description.",
                "highlight": "",
                "impact": "",
            }
        ]
    if not gaps:
        gaps = [
            {
                "text": "No specific gaps were identified in this evaluation pass.",
                "missing": "",
                "expected": "Strengthen your answer using the rubric bullets and cited job description requirements.",
                "jd_alignment": "",
                "improvement": "",
            }
        ]

    out["strengths"] = strengths
    out["gaps"] = gaps
    out["score_reasoning"] = str(out.get("score_reasoning") or "").strip()

    # Re-align cited lists to strengths/gaps text (same length, valid nested cites only)
    sc_old = out.get("strengths_cited") or []
    gc_old = out.get("gaps_cited") or []
    out["strengths_cited"] = []
    for i, s in enumerate(strengths):
        old = sc_old[i] if i < len(sc_old) and isinstance(sc_old[i], dict) else {}
        cites = [
            c
            for c in (old.get("citations") or [])
            if isinstance(c, dict) and _filter_citation_dict(c, allowed)
        ]
        out["strengths_cited"].append({"text": s["text"], "citations": cites})

    out["gaps_cited"] = []
    for i, g in enumerate(gaps):
        old = gc_old[i] if i < len(gc_old) and isinstance(gc_old[i], dict) else {}
        cites = [
            c
            for c in (old.get("citations") or [])
            if isinstance(c, dict) and _filter_citation_dict(c, allowed)
        ]
        out["gaps_cited"].append({"text": g["text"], "citations": cites})

    out["rubric_scores"] = _normalize_rubric_scores_list(out.get("rubric_scores"))

    return out


def evaluate_answer(
    question: str,
    question_type: str,
    focus_area: str,
    what_good_looks_like: list[str],
    must_mention: list[str],
    role_profile: dict,
    user_answer: str,
    evidence: list[dict],
    competency_label: str | None = None,
    document_rubric_json: list[dict] | None = None,
    evaluation_mode: str = "full",
    evaluation_cache_document_id: uuid.UUID | None = None,
) -> dict:
    """
    Evidence-cited, competency-aware evaluation of a candidate answer.

    Returns dict with:
      score (float 0-10),
      summary (str, why the score was given),
      score_reasoning (str, rubric-tied why this score),
      strengths: list of {text, evidence, highlight, impact},
      gaps: list of {text, missing, expected, jd_alignment, improvement},
      citations: list of {chunk_id, page_number, text},
      strengths_cited, gaps_cited (legacy cited shape for API),
      improved_answer (full rewrite targeting 9–10/10 per prompt rules),
      rubric_scores: list of {name, score, reasoning} when document JD dimensions are provided,
      follow_up_questions, suggested_followup, evidence_used,
      plus evidence_for_scoring added by the caller stack.

    Parsed output is passed through :func:`validate_evaluation_output` (citation IDs,
    non-empty strengths/gaps). One retry is attempted if all model citations were invalid.

    Model: :attr:`settings.openai_eval_chat_model` (default ``MODEL_FAST``;
    when ``USE_HIGH_QUALITY_EVAL`` is true, uses ``MODEL_HIGH_QUALITY``).
    """
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    rp = role_profile or DEFAULT_ROLE_PROFILE.copy()
    mode = (evaluation_mode or "full").strip().lower()
    if mode not in ("lite", "full"):
        mode = "full"

    # Canonical {chunk_id, text, page_number, section_type} for prompt + citation_indices
    evidence_norm = normalize_evaluation_evidence(evidence or [])

    eval_cache_key: str | None = None
    if (
        evaluation_cache_document_id
        and settings.cache_ttl_evaluation_seconds > 0
    ):
        eval_cache_key = evaluation_cache_key(
            evaluation_cache_document_id,
            question,
            user_answer,
            document_rubric_json,
            evaluation_mode=mode,
        )
        cached_eval = cache_get_json(eval_cache_key)
        if isinstance(cached_eval, dict):
            parsed = copy.deepcopy(cached_eval)
            parsed = validate_evaluation_output(parsed, evidence_norm, mode)
            if mode != "lite":
                parsed["strengths"] = enrich_strength_highlights(parsed.get("strengths") or [], user_answer)
            parsed["evidence_for_scoring"] = list(evidence_norm)
            return parsed

    system_prompt, user_content = _build_domain_aware_evaluation_prompt(
        question=question,
        question_type=question_type,
        focus_area=focus_area,
        competency_label=competency_label,
        what_good_looks_like=what_good_looks_like or [],
        must_mention=must_mention or [],
        evidence=evidence_norm,
        role_profile=rp,
        answer_text=user_answer,
        document_rubric_json=document_rubric_json,
        evaluation_mode=mode,
    )

    client = OpenAI(api_key=settings.openai_api_key)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    if mode == "lite":
        eval_max_tokens = min(900, max(settings.max_completion_tokens * 3, 500))
    else:
        eval_max_tokens = min(2048, max(settings.max_completion_tokens * 4, 1200))
    eval_model = settings.openai_eval_chat_model
    response = client.chat.completions.create(
        model=eval_model,
        messages=messages,
        max_tokens=eval_max_tokens,
    )

    raw = (response.choices[0].message.content or "").strip()
    parsed = _parse_evaluation_response(raw, evidence_norm)
    llm_citation_attempts = int(parsed.pop("_llm_citation_entries", 0) or 0)
    parsed = validate_evaluation_output(parsed, evidence_norm, mode)
    if mode != "lite":
        parsed["strengths"] = enrich_strength_highlights(parsed.get("strengths") or [], user_answer)
    citation_count_after = len(parsed.get("citations") or [])

    # Retry once if the model cited chunk_ids not in context (all filtered) but chunks exist (full mode only)
    if (
        mode != "lite"
        and llm_citation_attempts > 0
        and citation_count_after == 0
        and evidence_norm
    ):
        retry_user = (
            user_content
            + "\n\nIMPORTANT: Your previous reply listed citation chunk_ids that do not appear in "
            'the "Retrieved job description chunks" section. Every citations[].chunk_id must match '
            "a chunk_id from that section exactly. Return JSON only."
        )
        response = client.chat.completions.create(
            model=eval_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": retry_user},
            ],
            max_tokens=eval_max_tokens,
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = _parse_evaluation_response(raw, evidence_norm)
        parsed.pop("_llm_citation_entries", None)
        parsed = validate_evaluation_output(parsed, evidence_norm, mode)
        parsed["strengths"] = enrich_strength_highlights(parsed.get("strengths") or [], user_answer)

    if eval_cache_key and settings.cache_ttl_evaluation_seconds > 0:
        to_cache = copy.deepcopy(parsed)
        cache_set_json(eval_cache_key, to_cache, settings.cache_ttl_evaluation_seconds)

    parsed["evidence_for_scoring"] = list(evidence_norm)
    return parsed


AUXILIARY_SOURCE_TYPES = ["resume", "company", "notes"]


async def _has_auxiliary_sources(
    db: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> bool:
    """True if document has resume/company/notes sources or user has account-level resume."""
    from sqlalchemy import func
    r = await db.execute(
        select(func.count()).select_from(InterviewSource).where(
            InterviewSource.document_id == document_id,
            InterviewSource.source_type.in_(AUXILIARY_SOURCE_TYPES),
        )
    )
    if (r.scalar() or 0) > 0:
        return True
    if user_id and await get_user_resume_document_id(db, user_id):
        return True
    return False


async def _retrieve_auxiliary_evidence(
    db: AsyncSession,
    document_id: uuid.UUID,
    query: str,
    top_k: int = 4,
    user_id: uuid.UUID | None = None,
) -> list[dict]:
    """Retrieve from resume/company/notes (incl. user's account resume) for tailored phrasing."""
    additional_ids: list[uuid.UUID] = []
    if user_id:
        resume_doc_id = await get_user_resume_document_id(db, user_id)
        if resume_doc_id:
            additional_ids.append(resume_doc_id)
    query_embedding = embed_query(query)
    chunks = await retrieve_chunks(
        db=db,
        document_id=document_id,
        query_embedding=query_embedding,
        query_text=query,
        top_k=top_k,
        include_low_signal=False,
        section_types=None,
        doc_domain=None,
        source_types=AUXILIARY_SOURCE_TYPES,
        additional_document_ids=additional_ids if additional_ids else None,
    )
    return [_retrieval_dict_to_evidence_item(c) for c in chunks]


async def _retrieve_evidence_for_evaluation_query(
    db: AsyncSession,
    document_id: uuid.UUID,
    question: str,
    user_answer: str,
    competency_label: str | None,
    focus_area: str | None,
    top_k: int | None = None,
    session_pool: list[dict] | None = None,
) -> list[dict]:
    """
    Retrieve top relevant JD chunks for the evaluation prompt (question + answer + competency).

    When ``session_pool`` is provided (non-empty), re-ranks that pool with no vector query.

    Otherwise cached by (document_id + question text hash) when CACHE_TTL_RETRIEVAL_SECONDS > 0,
    then embed + retrieve_chunks.
    """
    k = top_k if top_k is not None else EVALUATION_QUERY_TOP_K
    parts = [question, (user_answer or "")[:500], competency_label or "", focus_area or ""]
    query_text = " ".join(p.strip() for p in parts if p and str(p).strip()).strip() or "job description requirements"

    if session_pool is not None and len(session_pool) > 0:
        ranked = _rank_pool_for_query(session_pool, query_text, k)
        if ranked:
            return ranked

    retrieval_key: str | None = None
    if settings.cache_ttl_retrieval_seconds > 0:
        retrieval_key = retrieval_cache_key(document_id, question)
        cached = await asyncio.to_thread(cache_get_json, retrieval_key)
        if isinstance(cached, list):
            return cached

    query_embedding = embed_query(query_text)
    chunks = await retrieve_chunks(
        db=db,
        document_id=document_id,
        query_embedding=query_embedding,
        query_text=query_text,
        top_k=k,
        include_low_signal=False,
        section_types=None,
        doc_domain="job_description",
        source_types=["jd"],
    )
    result = [_retrieval_dict_to_evidence_item(c) for c in chunks]
    if retrieval_key and settings.cache_ttl_retrieval_seconds > 0:
        await asyncio.to_thread(
            cache_set_json,
            retrieval_key,
            result,
            settings.cache_ttl_retrieval_seconds,
        )
    return result


async def evaluate_answer_with_retrieval(
    db: AsyncSession,
    document_id: uuid.UUID,
    user_id: uuid.UUID | None,
    question: str,
    question_type: str,
    focus_area: str,
    competency_id: str | None,
    competency_label: str | None,
    evidence_chunk_ids: list[str],
    what_good_looks_like: list[str],
    must_mention: list[str],
    role_profile: dict,
    user_answer: str,
    evidence: list[dict],
    evaluation_mode: str = "full",
    session_id: uuid.UUID | None = None,
) -> dict:
    """
    Evaluate with question-linked evidence. Merges rubric chunks, optional competency
    and auxiliary retrieval, then top relevant JD chunks for (question + answer + competency),
    normalizes to citation-ready shapes, and calls :func:`evaluate_answer`.

    When ``session_id`` is set, JD chunks are cached per session (one vector retrieval per session);
    per-question relevance uses re-ranking from that pool instead of a separate vector query.
    """
    session_pool: list[dict] | None = None
    if session_id is not None:
        try:
            session_pool = await _get_or_create_session_jd_pool(
                db, document_id, session_id, role_profile
            )
        except Exception as e:
            logger.warning("Session JD pool retrieval failed: %s", e)
            session_pool = []

    ev = list(evidence or [])
    seen = {str(e.get("chunk_id") or e.get("chunkId", "")) for e in ev}

    # Thin JD evidence: prefer session pool (no extra vector query), then competency retrieval
    if len(ev) < 2 and competency_label:
        if session_pool:
            try:
                extra = _rank_pool_for_query(session_pool, competency_label, COMPETENCY_EVIDENCE_TOP_K)
                for e in extra:
                    cid = str(e.get("chunk_id") or e.get("chunkId", ""))
                    if cid and cid not in seen:
                        seen.add(cid)
                        ev.append(e)
            except Exception as e:
                logger.warning("Session pool competency fill failed: %s", e)
        if len(ev) < 2:
            try:
                extra = await _retrieve_evidence_for_competency(
                    db=db,
                    document_id=document_id,
                    competency_label=competency_label,
                )
                for e in extra:
                    cid = str(e.get("chunk_id") or e.get("chunkId", ""))
                    if cid and cid not in seen:
                        seen.add(cid)
                        ev.append(e)
            except Exception as e:
                logger.warning("Optional retrieval for evaluation failed: %s", e)

    # Auxiliary sources: retrieve for tailored phrasing (resume, company, notes, incl. user account resume)
    try:
        if await _has_auxiliary_sources(db, document_id, user_id):
            query = f"{competency_label or focus_area or ''} {user_answer[:200]}".strip() or "experience skills"
            auxiliary = await _retrieve_auxiliary_evidence(db, document_id, query, top_k=4, user_id=user_id)
            for e in auxiliary:
                cid = str(e.get("chunk_id") or e.get("chunkId", ""))
                if cid and cid not in seen:
                    seen.add(cid)
                    ev.append(e)
    except Exception as e:
        logger.warning("Auxiliary retrieval for evaluation failed: %s", e)

    # Top relevant JD chunks for evaluation (question + answer + competency)
    try:
        query_ev = await _retrieve_evidence_for_evaluation_query(
            db=db,
            document_id=document_id,
            question=question,
            user_answer=user_answer,
            competency_label=competency_label,
            focus_area=focus_area,
            session_pool=session_pool if session_pool else None,
        )
        for e in query_ev:
            cid = str(e.get("chunk_id") or e.get("chunkId", ""))
            if cid and cid not in seen:
                seen.add(cid)
                ev.append(e)
    except Exception as e:
        logger.warning("Evaluation query retrieval failed: %s", e)

    doc_rubric: list[dict] | None = None
    try:
        doc_r = await db.execute(select(Document).where(Document.id == document_id))
        doc_row = doc_r.scalar_one_or_none()
        raw_rj = getattr(doc_row, "rubric_json", None) if doc_row else None
        if isinstance(raw_rj, list) and raw_rj:
            doc_rubric = [x for x in raw_rj if isinstance(x, dict) and str(x.get("name", "")).strip()]
            if not doc_rubric:
                doc_rubric = None
    except Exception as e:
        logger.warning("Could not load document.rubric_json for evaluation: %s", e)

    return evaluate_answer(
        question=question,
        question_type=question_type,
        focus_area=focus_area,
        what_good_looks_like=what_good_looks_like or [],
        must_mention=must_mention or [],
        role_profile=role_profile or {},
        user_answer=user_answer,
        evidence=ev,
        competency_label=competency_label,
        document_rubric_json=doc_rubric,
        evaluation_mode=evaluation_mode,
        evaluation_cache_document_id=document_id,
    )
