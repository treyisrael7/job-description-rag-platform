"""Mode selection, hybrid orchestration, and production retrieve_chunks entry."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.retrieval.constants import MAX_RETRIEVAL_CHUNKS, RetrievalMode
from app.services.retrieval.keyword_db import retrieve_chunks_keyword
from app.services.retrieval.merge_mmr import (
    _allocate_jd_resume_slots,
    _finalize_single_source_candidates,
    _log_retrieval_summary,
    _merge_retrieval_candidates,
    _mmr_select,
    _split_slot_targets,
)
from app.services.retrieval.payloads import _finalize_chunks, _with_retrieval_source_defaults
from app.services.retrieval.semantic import _retrieve_semantic_candidates

logger = logging.getLogger(__name__)


def get_default_retrieval_mode() -> RetrievalMode:
    """Return the retrieval mode implied by current app settings."""
    return "hybrid" if settings.hybrid_retrieval_enabled else "semantic"


async def retrieve_chunks_for_mode(
    db: AsyncSession,
    document_id: uuid.UUID,
    query_embedding: list[float] | None,
    top_k: int,
    mode: RetrievalMode = "hybrid",
    include_low_signal: bool = False,
    section_types: list[str] | None = None,
    doc_domain: str | None = None,
    source_types: list[str] | None = None,
    additional_document_ids: list[uuid.UUID] | None = None,
    query_text: str | None = None,
    *,
    enforce_production_chunk_budget: bool = False,
) -> list[dict]:
    """
    Shared retrieval entry point used by eval tooling and production callers.

    Behavior:
    - `semantic`: vector retrieval + MMR
    - `keyword`: PostgreSQL full-text retrieval (+ MMR when a query embedding is provided)
    - `hybrid`: semantic retrieval plus keyword augmentation and merge

    When ``enforce_production_chunk_budget`` is True (production ``retrieve_chunks`` only),
    total returned chunks never exceeds ``MAX_RETRIEVAL_CHUNKS``; with resume documents,
    retrieval targets an even JD/resume split and reallocates empty slots to the richer side.
    """
    normalized_query_text = (query_text or "").strip()

    if mode not in ("hybrid", "semantic", "keyword"):
        raise ValueError(f"Unsupported retrieval mode: {mode}")

    if mode in ("hybrid", "semantic") and query_embedding is None:
        raise ValueError(f"query_embedding is required for retrieval mode '{mode}'")

    # Hard cap when the production path asks for it; eval callers pass enforce_production_chunk_budget=False.
    budget = min(top_k, MAX_RETRIEVAL_CHUNKS) if enforce_production_chunk_budget else top_k
    extra = additional_document_ids or []
    use_jd_resume_split = bool(enforce_production_chunk_budget and extra)
    # Wider SQL limits keep enough high-similarity candidates for MMR before the hard token cap.
    pool_limit = max(budget, settings.top_n_candidates) if enforce_production_chunk_budget else None

    if mode == "semantic":
        if use_jd_resume_split:
            sem_p = await _retrieve_semantic_candidates(
                db=db,
                document_id=document_id,
                query_embedding=query_embedding,
                top_k=budget,
                include_low_signal=include_low_signal,
                section_types=section_types,
                doc_domain=doc_domain,
                source_types=source_types,
                additional_document_ids=additional_document_ids,
                _scope="primary",
                _sql_limit_override=pool_limit,
            )
            sem_a = await _retrieve_semantic_candidates(
                db=db,
                document_id=document_id,
                query_embedding=query_embedding,
                top_k=budget,
                include_low_signal=include_low_signal,
                section_types=section_types,
                doc_domain=doc_domain,
                source_types=source_types,
                additional_document_ids=additional_document_ids,
                _scope="additional",
                _sql_limit_override=pool_limit,
            )
            slot_p, slot_a = _split_slot_targets(budget, has_additional=True)
            allocated = _allocate_jd_resume_slots(
                sem_p,
                sem_a,
                max_total=budget,
                slot_primary=slot_p,
                slot_additional=slot_a,
            )
            final_candidates = _with_retrieval_source_defaults(
                _mmr_select(allocated, query_embedding, budget, settings.mmr_lambda)
                if allocated
                else [],
                "semantic",
            )
            _log_retrieval_summary(
                document_id=document_id,
                semantic_hits=len(sem_p) + len(sem_a),
                keyword_hits=0,
                deduped_hits=len(allocated),
                final_hits=len(final_candidates),
                hybrid_enabled=False,
            )
            return _finalize_chunks(
                final_candidates,
                primary_document_id=document_id,
                additional_document_ids=additional_document_ids,
            )

        semantic_candidates = await _retrieve_semantic_candidates(
            db=db,
            document_id=document_id,
            query_embedding=query_embedding,
            top_k=budget,
            include_low_signal=include_low_signal,
            section_types=section_types,
            doc_domain=doc_domain,
            source_types=source_types,
            additional_document_ids=additional_document_ids,
        )
        final_candidates = _with_retrieval_source_defaults(
            _mmr_select(semantic_candidates, query_embedding, budget, settings.mmr_lambda)
            if semantic_candidates
            else [],
            "semantic",
        )
        _log_retrieval_summary(
            document_id=document_id,
            semantic_hits=len(semantic_candidates),
            keyword_hits=0,
            deduped_hits=len(semantic_candidates),
            final_hits=len(final_candidates),
            hybrid_enabled=False,
        )
        return _finalize_chunks(
            final_candidates,
            primary_document_id=document_id,
            additional_document_ids=additional_document_ids,
        )

    if mode == "keyword":
        if not normalized_query_text:
            _log_retrieval_summary(
                document_id=document_id,
                semantic_hits=0,
                keyword_hits=0,
                deduped_hits=0,
                final_hits=0,
                hybrid_enabled=False,
            )
            return []
        kw_limit = (
            pool_limit
            if pool_limit is not None
            else max(budget, settings.top_n_candidates)
        )
        if use_jd_resume_split:
            kw_p = await retrieve_chunks_keyword(
                db=db,
                document_id=document_id,
                query_text=normalized_query_text,
                top_k=kw_limit,
                include_low_signal=include_low_signal,
                section_types=section_types,
                doc_domain=doc_domain,
                source_types=source_types,
                additional_document_ids=additional_document_ids,
                _scope="primary",
                _sql_limit_override=kw_limit,
            )
            kw_a = await retrieve_chunks_keyword(
                db=db,
                document_id=document_id,
                query_text=normalized_query_text,
                top_k=kw_limit,
                include_low_signal=include_low_signal,
                section_types=section_types,
                doc_domain=doc_domain,
                source_types=source_types,
                additional_document_ids=additional_document_ids,
                _scope="additional",
                _sql_limit_override=kw_limit,
            )
            slot_p, slot_a = _split_slot_targets(budget, has_additional=True)
            allocated = _allocate_jd_resume_slots(
                kw_p,
                kw_a,
                max_total=budget,
                slot_primary=slot_p,
                slot_additional=slot_a,
            )
            final_candidates = _finalize_single_source_candidates(
                allocated,
                query_embedding=query_embedding,
                top_k=budget,
                retrieval_source="keyword",
                primary_document_id=document_id,
                additional_document_ids=additional_document_ids,
            )
            _log_retrieval_summary(
                document_id=document_id,
                semantic_hits=0,
                keyword_hits=len(kw_p) + len(kw_a),
                deduped_hits=len(allocated),
                final_hits=len(final_candidates),
                hybrid_enabled=False,
            )
            return final_candidates

        keyword_candidates = await retrieve_chunks_keyword(
            db=db,
            document_id=document_id,
            query_text=normalized_query_text,
            top_k=kw_limit,
            include_low_signal=include_low_signal,
            section_types=section_types,
            doc_domain=doc_domain,
            source_types=source_types,
            additional_document_ids=additional_document_ids,
        )
        final_candidates = _finalize_single_source_candidates(
            keyword_candidates,
            query_embedding=query_embedding,
            top_k=budget,
            retrieval_source="keyword",
            primary_document_id=document_id,
            additional_document_ids=additional_document_ids,
        )
        _log_retrieval_summary(
            document_id=document_id,
            semantic_hits=0,
            keyword_hits=len(keyword_candidates),
            deduped_hits=len(keyword_candidates),
            final_hits=len(final_candidates),
            hybrid_enabled=False,
        )
        return final_candidates

    # --- hybrid ---
    if use_jd_resume_split:
        sem_p = await _retrieve_semantic_candidates(
            db=db,
            document_id=document_id,
            query_embedding=query_embedding,
            top_k=budget,
            include_low_signal=include_low_signal,
            section_types=section_types,
            doc_domain=doc_domain,
            source_types=source_types,
            additional_document_ids=additional_document_ids,
            _scope="primary",
            _sql_limit_override=pool_limit,
        )
        sem_a = await _retrieve_semantic_candidates(
            db=db,
            document_id=document_id,
            query_embedding=query_embedding,
            top_k=budget,
            include_low_signal=include_low_signal,
            section_types=section_types,
            doc_domain=doc_domain,
            source_types=source_types,
            additional_document_ids=additional_document_ids,
            _scope="additional",
            _sql_limit_override=pool_limit,
        )
        semantic_hits = len(sem_p) + len(sem_a)

        if not normalized_query_text:
            slot_p, slot_a = _split_slot_targets(budget, has_additional=True)
            allocated = _allocate_jd_resume_slots(
                sem_p,
                sem_a,
                max_total=budget,
                slot_primary=slot_p,
                slot_additional=slot_a,
            )
            final_candidates = _with_retrieval_source_defaults(
                _mmr_select(allocated, query_embedding, budget, settings.mmr_lambda)
                if allocated
                else [],
                "semantic",
            )
            _log_retrieval_summary(
                document_id=document_id,
                semantic_hits=semantic_hits,
                keyword_hits=0,
                deduped_hits=len(allocated),
                final_hits=len(final_candidates),
                hybrid_enabled=True,
            )
            return _finalize_chunks(
                final_candidates,
                primary_document_id=document_id,
                additional_document_ids=additional_document_ids,
            )

        kw_limit_h = pool_limit if pool_limit is not None else max(budget, settings.top_n_candidates)
        try:
            kw_p = await retrieve_chunks_keyword(
                db=db,
                document_id=document_id,
                query_text=normalized_query_text,
                top_k=kw_limit_h,
                include_low_signal=include_low_signal,
                section_types=section_types,
                doc_domain=doc_domain,
                source_types=source_types,
                additional_document_ids=additional_document_ids,
                _scope="primary",
                _sql_limit_override=kw_limit_h,
            )
            kw_a = await retrieve_chunks_keyword(
                db=db,
                document_id=document_id,
                query_text=normalized_query_text,
                top_k=kw_limit_h,
                include_low_signal=include_low_signal,
                section_types=section_types,
                doc_domain=doc_domain,
                source_types=source_types,
                additional_document_ids=additional_document_ids,
                _scope="additional",
                _sql_limit_override=kw_limit_h,
            )
        except Exception as exc:
            logger.warning("Keyword retrieval failed; falling back to semantic-only: %s", exc)
            slot_p, slot_a = _split_slot_targets(budget, has_additional=True)
            allocated = _allocate_jd_resume_slots(
                sem_p,
                sem_a,
                max_total=budget,
                slot_primary=slot_p,
                slot_additional=slot_a,
            )
            final_candidates = _with_retrieval_source_defaults(
                _mmr_select(allocated, query_embedding, budget, settings.mmr_lambda)
                if allocated
                else [],
                "semantic",
            )
            _log_retrieval_summary(
                document_id=document_id,
                semantic_hits=semantic_hits,
                keyword_hits=0,
                deduped_hits=len(allocated),
                final_hits=len(final_candidates),
                hybrid_enabled=True,
            )
            return _finalize_chunks(
                final_candidates,
                primary_document_id=document_id,
                additional_document_ids=additional_document_ids,
            )

        if not kw_p and not kw_a:
            slot_p, slot_a = _split_slot_targets(budget, has_additional=True)
            allocated = _allocate_jd_resume_slots(
                sem_p,
                sem_a,
                max_total=budget,
                slot_primary=slot_p,
                slot_additional=slot_a,
            )
            final_candidates = _with_retrieval_source_defaults(
                _mmr_select(allocated, query_embedding, budget, settings.mmr_lambda)
                if allocated
                else [],
                "semantic",
            )
            _log_retrieval_summary(
                document_id=document_id,
                semantic_hits=semantic_hits,
                keyword_hits=0,
                deduped_hits=len(allocated),
                final_hits=len(final_candidates),
                hybrid_enabled=True,
            )
            return _finalize_chunks(
                final_candidates,
                primary_document_id=document_id,
                additional_document_ids=additional_document_ids,
            )

        merged_p = _merge_retrieval_candidates(sem_p, kw_p)
        merged_a = _merge_retrieval_candidates(sem_a, kw_a)
        slot_p, slot_a = _split_slot_targets(budget, has_additional=True)
        allocated = _allocate_jd_resume_slots(
            merged_p,
            merged_a,
            max_total=budget,
            slot_primary=slot_p,
            slot_additional=slot_a,
        )
        diversified = _mmr_select(
            allocated,
            query_embedding,
            budget,
            settings.mmr_lambda,
        )
        _log_retrieval_summary(
            document_id=document_id,
            semantic_hits=semantic_hits,
            keyword_hits=len(kw_p) + len(kw_a),
            deduped_hits=len(allocated),
            final_hits=len(diversified),
            hybrid_enabled=True,
        )
        return _finalize_chunks(
            diversified,
            primary_document_id=document_id,
            additional_document_ids=additional_document_ids,
        )

    semantic_candidates = await _retrieve_semantic_candidates(
        db=db,
        document_id=document_id,
        query_embedding=query_embedding,
        top_k=budget,
        include_low_signal=include_low_signal,
        section_types=section_types,
        doc_domain=doc_domain,
        source_types=source_types,
        additional_document_ids=additional_document_ids,
    )

    if not normalized_query_text:
        final_candidates = _with_retrieval_source_defaults(
            _mmr_select(semantic_candidates, query_embedding, budget, settings.mmr_lambda)
            if semantic_candidates
            else [],
            "semantic",
        )
        _log_retrieval_summary(
            document_id=document_id,
            semantic_hits=len(semantic_candidates),
            keyword_hits=0,
            deduped_hits=len(semantic_candidates),
            final_hits=len(final_candidates),
            hybrid_enabled=True,
        )
        return _finalize_chunks(
            final_candidates,
            primary_document_id=document_id,
            additional_document_ids=additional_document_ids,
        )

    kw_limit_u = max(budget, settings.top_n_candidates)
    try:
        keyword_candidates = await retrieve_chunks_keyword(
            db=db,
            document_id=document_id,
            query_text=normalized_query_text,
            top_k=kw_limit_u,
            include_low_signal=include_low_signal,
            section_types=section_types,
            doc_domain=doc_domain,
            source_types=source_types,
            additional_document_ids=additional_document_ids,
        )
    except Exception as exc:
        logger.warning("Keyword retrieval failed; falling back to semantic-only: %s", exc)
        final_candidates = _with_retrieval_source_defaults(
            _mmr_select(semantic_candidates, query_embedding, budget, settings.mmr_lambda)
            if semantic_candidates
            else [],
            "semantic",
        )
        _log_retrieval_summary(
            document_id=document_id,
            semantic_hits=len(semantic_candidates),
            keyword_hits=0,
            deduped_hits=len(semantic_candidates),
            final_hits=len(final_candidates),
            hybrid_enabled=True,
        )
        return _finalize_chunks(
            final_candidates,
            primary_document_id=document_id,
            additional_document_ids=additional_document_ids,
        )

    if not keyword_candidates:
        final_candidates = _with_retrieval_source_defaults(
            _mmr_select(semantic_candidates, query_embedding, budget, settings.mmr_lambda)
            if semantic_candidates
            else [],
            "semantic",
        )
        _log_retrieval_summary(
            document_id=document_id,
            semantic_hits=len(semantic_candidates),
            keyword_hits=0,
            deduped_hits=len(semantic_candidates),
            final_hits=len(final_candidates),
            hybrid_enabled=True,
        )
        return _finalize_chunks(
            final_candidates,
            primary_document_id=document_id,
            additional_document_ids=additional_document_ids,
        )

    hybrid_candidates = _merge_retrieval_candidates(semantic_candidates, keyword_candidates)
    diversified = _mmr_select(
        hybrid_candidates,
        query_embedding,
        budget,
        settings.mmr_lambda,
    )
    _log_retrieval_summary(
        document_id=document_id,
        semantic_hits=len(semantic_candidates),
        keyword_hits=len(keyword_candidates),
        deduped_hits=len(hybrid_candidates),
        final_hits=len(diversified),
        hybrid_enabled=True,
    )
    return _finalize_chunks(
        diversified,
        primary_document_id=document_id,
        additional_document_ids=additional_document_ids,
    )


async def retrieve_chunks(
    db: AsyncSession,
    document_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    include_low_signal: bool = False,
    section_types: list[str] | None = None,
    doc_domain: str | None = None,
    source_types: list[str] | None = None,
    additional_document_ids: list[uuid.UUID] | None = None,
    query_text: str | None = None,
) -> list[dict]:
    """
    Shared production retrieval entry point used by ask/retrieve/interview flows.

    Caps ``top_k`` at ``MAX_RETRIEVAL_CHUNKS`` (token / cost optimization). With
    ``additional_document_ids``, JD and resume are retrieved in a balanced split
    inside ``retrieve_chunks_for_mode(..., enforce_production_chunk_budget=True)``.

    Eval tooling should call ``retrieve_chunks_for_mode()`` without the budget flag
    when comparing retrieval modes at large ``top_k``.

    Returned chunks include ``document_id`` and ``documentId`` (UUID string),
    ``source_type`` in ``{"JD", "RESUME", "OTHER"}`` (primary vs
    ``additional_document_ids`` vs neither), and ``section_type`` when present.
    Interview attachment metadata remains on ``sourceType`` / ``sourceTitle``.
    """
    effective_top_k = min(top_k, MAX_RETRIEVAL_CHUNKS)
    return await retrieve_chunks_for_mode(
        db=db,
        document_id=document_id,
        query_embedding=query_embedding,
        top_k=effective_top_k,
        mode=get_default_retrieval_mode(),
        include_low_signal=include_low_signal,
        section_types=section_types,
        doc_domain=doc_domain,
        source_types=source_types,
        additional_document_ids=additional_document_ids,
        query_text=query_text,
        enforce_production_chunk_budget=True,
    )
