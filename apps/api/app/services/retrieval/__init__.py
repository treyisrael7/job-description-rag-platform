"""Retrieval: embed query, search document_chunks, hybrid merge, MMR diversification."""

from app.services.retrieval.constants import MAX_RETRIEVAL_CHUNKS, RetrievalMode
from app.services.retrieval.embeddings import embed_query
from app.services.retrieval.keyword_db import retrieve_chunks_keyword
from app.services.retrieval.keyword_query import _normalize_keyword_query_text, suggest_section_filters
from app.services.retrieval.merge_mmr import _allocate_jd_resume_slots, _split_slot_targets
from app.services.retrieval.orchestration import (
    get_default_retrieval_mode,
    retrieve_chunks,
    retrieve_chunks_for_mode,
)
from app.services.retrieval.semantic import _retrieve_semantic_candidates

__all__ = [
    "MAX_RETRIEVAL_CHUNKS",
    "RetrievalMode",
    "_allocate_jd_resume_slots",
    "_normalize_keyword_query_text",
    "_retrieve_semantic_candidates",
    "_split_slot_targets",
    "embed_query",
    "get_default_retrieval_mode",
    "retrieve_chunks",
    "retrieve_chunks_for_mode",
    "retrieve_chunks_keyword",
    "suggest_section_filters",
]
