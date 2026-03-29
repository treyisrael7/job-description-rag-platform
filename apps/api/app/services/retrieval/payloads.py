"""Chunk payload shaping for API responses."""

import uuid

from app.services.retrieval.constants import SECTION_TYPE_EXPANSION


def _expanded_section_types(section_types: list[str] | None) -> list[str] | None:
    """Expand canonical section filters to match legacy section names stored in DB."""
    if not section_types:
        return None

    expanded: set[str] = set()
    for st in section_types:
        expanded.add(st)
        expanded.update(SECTION_TYPE_EXPANSION.get(st, []))
    return list(expanded)


def _chunk_document_role(
    chunk: dict,
    *,
    primary_document_id: uuid.UUID,
    additional_document_ids: list[uuid.UUID] | None,
) -> tuple[str, str]:
    """Map chunk to (document_id str, logical source_type: JD | RESUME | OTHER)."""
    raw = chunk.get("document_id")
    if raw is None:
        return str(primary_document_id), "JD"
    doc_uuid = uuid.UUID(str(raw))
    if doc_uuid == primary_document_id:
        return str(doc_uuid), "JD"
    if doc_uuid in set(additional_document_ids or []):
        return str(doc_uuid), "RESUME"
    return str(doc_uuid), "OTHER"


def _chunk_payload_from_row(row) -> dict:
    """Normalize a SQL row into the shared retrieval payload used across retrieval paths."""
    source_type_val = getattr(row, "src_type", None) or "jd"
    source_title_val = getattr(row, "src_title", None) or ""
    payload = {
        "chunk_id": str(row.id),
        "chunkId": str(row.id),
        "page_number": row.page_number,
        "page": row.page_number,
        "snippet": row.content,
        "text": row.content,
        "score": round(float(row.score), 6),
        "is_low_signal": bool(row.is_low_signal),
        "section_type": getattr(row, "section_type", None),
        "sourceType": source_type_val,
        "sourceTitle": source_title_val,
    }
    doc_id = getattr(row, "document_id", None)
    if doc_id is not None:
        payload["document_id"] = str(doc_id)
    embedding = getattr(row, "embedding", None)
    if embedding is not None:
        payload["embedding"] = embedding
    content_hash = getattr(row, "content_hash", None)
    if content_hash:
        payload["content_hash"] = content_hash
    return payload


def _with_retrieval_source_defaults(candidates: list[dict], retrieval_source: str) -> list[dict]:
    """Attach transparency metadata for single-source retrieval results."""
    result = []
    for candidate in candidates:
        enriched = dict(candidate)
        enriched["retrieval_source"] = retrieval_source
        enriched["retrievalSource"] = retrieval_source
        if retrieval_source == "semantic":
            enriched["semantic_score"] = enriched.get("semantic_score", enriched.get("score"))
            enriched["keyword_score"] = enriched.get("keyword_score")
        elif retrieval_source == "keyword":
            enriched["semantic_score"] = enriched.get("semantic_score")
            enriched["keyword_score"] = enriched.get("keyword_score", enriched.get("score"))
        enriched["final_score"] = enriched.get("final_score", enriched.get("score"))
        result.append(enriched)
    return result


def _finalize_chunks(
    candidates: list[dict],
    *,
    primary_document_id: uuid.UUID,
    additional_document_ids: list[uuid.UUID] | None = None,
) -> list[dict]:
    """Return caller-facing chunk dicts while preserving internal debugging metadata."""
    out: list[dict] = []
    for c in candidates:
        doc_id_str, logical_source = _chunk_document_role(
            c,
            primary_document_id=primary_document_id,
            additional_document_ids=additional_document_ids,
        )
        out.append(
            {
                "chunk_id": c["chunk_id"],
                "chunkId": c["chunkId"],
                "document_id": doc_id_str,
                "documentId": doc_id_str,
                "page_number": c["page_number"],
                "page": c["page"],
                "snippet": c["snippet"],
                "text": c["text"],
                "score": c["score"],
                "sourceType": c["sourceType"],
                "sourceTitle": c["sourceTitle"],
                "source_type": logical_source,
                "is_low_signal": c.get("is_low_signal", False),
                "section_type": c.get("section_type"),
                "retrieval_source": c.get("retrieval_source", "semantic"),
                "retrievalSource": c.get("retrievalSource", c.get("retrieval_source", "semantic")),
                "semantic_score": c.get(
                    "semantic_score",
                    c["score"] if c.get("retrieval_source", "semantic") == "semantic" else None,
                ),
                "keyword_score": c.get("keyword_score"),
                "final_score": c.get("final_score", c["score"]),
            }
        )
    return out
