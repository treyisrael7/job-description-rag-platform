"""Hybrid score merge, JD/resume slot allocation, and MMR diversification."""

import logging
import uuid

from app.core.config import settings
from app.services.retrieval.payloads import (
    _finalize_chunks,
    _with_retrieval_source_defaults,
)

logger = logging.getLogger(__name__)


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity (dot product for normalized vectors)."""
    return sum(x * y for x, y in zip(a, b))


def _normalize_scores(candidates: list[dict], score_key: str) -> None:
    """Normalize a retrieval list's scores into 0..1 so vector and FTS results can be merged."""
    positive_scores = [max(float(c.get(score_key, 0.0)), 0.0) for c in candidates]
    max_score = max(positive_scores, default=0.0)
    for c in candidates:
        raw = max(float(c.get(score_key, 0.0)), 0.0)
        c[f"{score_key}_norm"] = (raw / max_score) if max_score > 0 else 0.0


def _hybrid_score(semantic_norm: float | None, keyword_norm: float | None) -> float:
    """
    Blend semantic and keyword scores into one ranking score.

    Strategy:
    - semantic-only keeps its normalized semantic score
    - keyword-only gets a slight discount so exact-term matches complement, rather than dominate,
      vector retrieval
    - if both hit the same chunk, add a small corroboration bonus
    """
    if semantic_norm is not None and keyword_norm is not None:
        return round(
            min(1.0, max(semantic_norm, keyword_norm * 0.9) + 0.1 * min(semantic_norm, keyword_norm)),
            6,
        )
    if semantic_norm is not None:
        return round(float(semantic_norm), 6)
    if keyword_norm is not None:
        return round(float(keyword_norm) * 0.9, 6)
    return 0.0


def _merge_retrieval_candidates(
    semantic_candidates: list[dict],
    keyword_candidates: list[dict],
) -> list[dict]:
    """Merge semantic + keyword candidates and deduplicate by chunk id, falling back to content hash."""
    _normalize_scores(semantic_candidates, "score")
    for c in semantic_candidates:
        c["semantic_score"] = c["score"]
        c["semantic_score_norm"] = c.pop("score_norm")
        c["retrieval_source"] = "semantic"
        c["retrievalSource"] = "semantic"

    _normalize_scores(keyword_candidates, "score")
    for c in keyword_candidates:
        c["keyword_score"] = c["score"]
        c["keyword_score_norm"] = c.pop("score_norm")
        c["retrieval_source"] = "keyword"
        c["retrievalSource"] = "keyword"

    merged: dict[str, dict] = {}
    hash_to_chunk_id: dict[str, str] = {}

    for candidate in semantic_candidates + keyword_candidates:
        chunk_id = candidate["chunk_id"]
        content_hash = candidate.get("content_hash")
        existing_key = chunk_id
        if content_hash and content_hash in hash_to_chunk_id:
            existing_key = hash_to_chunk_id[content_hash]

        existing = merged.get(existing_key)
        if not existing:
            merged[existing_key] = dict(candidate)
            if content_hash:
                hash_to_chunk_id[content_hash] = existing_key
            continue

        if candidate.get("semantic_score") is not None:
            existing["semantic_score"] = candidate["semantic_score"]
            existing["semantic_score_norm"] = candidate.get("semantic_score_norm")
        if candidate.get("keyword_score") is not None:
            existing["keyword_score"] = candidate["keyword_score"]
            existing["keyword_score_norm"] = candidate.get("keyword_score_norm")
        if existing.get("embedding") is None and candidate.get("embedding") is not None:
            existing["embedding"] = candidate["embedding"]
        if not existing.get("content_hash") and content_hash:
            existing["content_hash"] = content_hash
            hash_to_chunk_id[content_hash] = existing_key
        if not existing.get("document_id") and candidate.get("document_id"):
            existing["document_id"] = candidate["document_id"]

        existing_source = existing.get("retrieval_source")
        candidate_source = candidate.get("retrieval_source")
        if existing_source == "both" or candidate_source == "both":
            existing["retrieval_source"] = "both"
            existing["retrievalSource"] = "both"
        elif existing_source and candidate_source and existing_source != candidate_source:
            existing["retrieval_source"] = "both"
            existing["retrievalSource"] = "both"

    merged_candidates = list(merged.values())
    for c in merged_candidates:
        c["final_score"] = _hybrid_score(
            c.get("semantic_score_norm"),
            c.get("keyword_score_norm"),
        )
        c["score"] = c["final_score"]

    merged_candidates.sort(key=lambda c: c["score"], reverse=True)
    return merged_candidates


def _allocate_jd_resume_slots(
    primary_chunks: list[dict],
    additional_chunks: list[dict],
    *,
    max_total: int,
    slot_primary: int,
    slot_additional: int,
) -> list[dict]:
    """
    Cost optimization: keep a fixed token budget by taking top similarity chunks per
    corpus (JD vs resume), then reassign empty slots to whichever side still has
    higher-ranked hits.

    Chunks are assumed pre-sorted by SQL (best similarity first); we re-sort by
    ``score`` descending defensively, then merge.
    """
    if max_total <= 0:
        return []

    primary_ranked = sorted(primary_chunks, key=lambda c: float(c.get("score") or 0.0), reverse=True)
    additional_ranked = sorted(
        additional_chunks, key=lambda c: float(c.get("score") or 0.0), reverse=True
    )

    take_p = min(slot_primary, len(primary_ranked))
    take_a = min(slot_additional, len(additional_ranked))
    chosen_p = primary_ranked[:take_p]
    chosen_a = additional_ranked[:take_a]
    spare = max_total - len(chosen_p) - len(chosen_a)

    rest_p = primary_ranked[take_p:]
    rest_a = additional_ranked[take_a:]
    spill: list[dict] = []
    i, j = 0, 0
    while len(spill) < spare and (i < len(rest_p) or j < len(rest_a)):
        sp = float(rest_p[i]["score"]) if i < len(rest_p) else -1.0
        sa = float(rest_a[j]["score"]) if j < len(rest_a) else -1.0
        if sp >= sa and i < len(rest_p):
            spill.append(rest_p[i])
            i += 1
        elif j < len(rest_a):
            spill.append(rest_a[j])
            j += 1
        else:
            spill.append(rest_p[i])
            i += 1

    merged = chosen_p + chosen_a + spill
    merged.sort(key=lambda c: float(c.get("score") or 0.0), reverse=True)
    return merged[:max_total]


def _split_slot_targets(
    max_total: int,
    *,
    has_additional: bool,
) -> tuple[int, int]:
    """
    Even JD / resume slot targets (e.g. 8 total -> 4+4); odd totals give the spare to primary.

    Cost optimization: avoids stuffing context from one document when the other still has
    strong matches after the initial per-side picks (see ``_allocate_jd_resume_slots``).
    """
    if not has_additional or max_total <= 0:
        return max_total, 0
    half = max_total // 2
    rem = max_total - 2 * half
    return half + rem, half


def _mmr_select(
    candidates: list[dict],
    query_embedding: list[float],
    top_k: int,
    lambda_: float,
) -> list[dict]:
    """
    Maximal Marginal Relevance: select diverse top_k from candidates.
    candidates have: id, page_number, content, embedding, score (sim to query).
    """
    if len(candidates) <= top_k:
        for c in candidates[:top_k]:
            c.pop("embedding", None)
        return candidates[:top_k]

    selected: list[dict] = []
    remaining = list(candidates)

    while len(selected) < top_k and remaining:
        best_idx = -1
        best_mmr = float("-inf")
        for i, c in enumerate(remaining):
            sim_q = c["score"]
            max_sim_sel = 0.0
            if selected and c.get("embedding") is not None:
                for s in selected:
                    if s.get("embedding") is None:
                        continue
                    sim_d = _cosine_sim(c["embedding"], s["embedding"])
                    max_sim_sel = max(max_sim_sel, sim_d)
            mmr = lambda_ * sim_q - (1 - lambda_) * max_sim_sel
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i
        if best_idx < 0:
            break
        chosen = remaining.pop(best_idx)
        selected.append(chosen)

    for c in selected:
        c.pop("embedding", None)
    return selected


def _finalize_single_source_candidates(
    candidates: list[dict],
    *,
    query_embedding: list[float] | None,
    top_k: int,
    retrieval_source: str,
    primary_document_id: uuid.UUID,
    additional_document_ids: list[uuid.UUID] | None = None,
) -> list[dict]:
    """Apply shared post-processing for semantic-only or keyword-only candidate lists."""
    ranked = candidates
    if query_embedding is not None and candidates:
        ranked = _mmr_select(candidates, query_embedding, top_k, settings.mmr_lambda)
    else:
        ranked = candidates[:top_k]
        for c in ranked:
            c.pop("embedding", None)
    return _finalize_chunks(
        _with_retrieval_source_defaults(ranked, retrieval_source),
        primary_document_id=primary_document_id,
        additional_document_ids=additional_document_ids,
    )


def _log_retrieval_summary(
    *,
    document_id: uuid.UUID,
    semantic_hits: int,
    keyword_hits: int,
    deduped_hits: int,
    final_hits: int,
    hybrid_enabled: bool,
) -> None:
    """Emit a compact structured log for hybrid retrieval debugging."""
    logger.info(
        "hybrid_retrieval_summary document_id=%s hybrid_enabled=%s semantic_hits=%s keyword_hits=%s deduped_hits=%s final_hits=%s",
        document_id,
        hybrid_enabled,
        semantic_hits,
        keyword_hits,
        deduped_hits,
        final_hits,
    )
