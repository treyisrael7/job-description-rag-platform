"""Ingest Interview Kit sources: resume (PDF/text), company (text/URL), notes (text)."""

import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document, DocumentChunk, InterviewSource
from app.services.chunking import chunk_pages
from app.services.ingestion import _create_embeddings
from app.services.storage import get_storage

logger = logging.getLogger(__name__)

VALID_SOURCE_TYPES = frozenset({"resume", "company", "notes"})
MAX_TEXT_CHARS = 100_000
MAX_URL_FETCH_CHARS = 50_000


def _extract_text_per_page(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Extract text per page using PyMuPDF."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        result = []
        limit = min(len(doc), settings.max_pdf_pages)
        for i in range(limit):
            page = doc[i]
            text = page.get_text(sort=True)
            result.append((i + 1, text))
        return result
    finally:
        doc.close()


async def ingest_text_source(
    db: AsyncSession,
    document_id: uuid.UUID,
    source_type: str,
    title: str,
    content: str,
) -> str:
    """
    Ingest pasted text (resume, company, notes). Chunk, embed, store.
    Returns source_id as string.
    """
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"Invalid source_type: {source_type}")
    if not title or not isinstance(title, str):
        title = source_type.replace("_", " ").title()
    content = (content or "").strip()
    if len(content) > MAX_TEXT_CHARS:
        content = content[:MAX_TEXT_CHARS]
    if not content:
        raise ValueError("Content is empty")

    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise ValueError("Document not found")

    page_texts = [(1, content)]
    chunk_results = chunk_pages(
        page_texts,
        min_chars=settings.min_chunk_chars,
        max_chunks=min(50, settings.max_chunks_per_doc),
    )
    if not chunk_results:
        raise ValueError("No chunks produced from content")

    texts = [c.content for c in chunk_results]
    embeddings = _create_embeddings(texts)
    if len(embeddings) != len(chunk_results):
        raise ValueError("Embedding count mismatch")

    source = InterviewSource(
        document_id=document_id,
        source_type=source_type,
        title=title.strip()[:200],
    )
    db.add(source)
    await db.flush()

    for i, (cr, emb) in enumerate(zip(chunk_results, embeddings)):
        chunk = DocumentChunk(
            document_id=document_id,
            source_id=source.id,
            chunk_index=i,
            content=cr.content,
            page_number=cr.page_number,
            section=cr.section_type,
            is_boilerplate=False,
            quality_score=cr.quality_score,
            is_low_signal=cr.is_low_signal,
            content_hash=cr.content_hash,
            section_type=cr.section_type,
            doc_domain="general",
            skills_detected=cr.skills_detected,
            embedding=emb,
        )
        db.add(chunk)

    if source_type == "resume":
        from app.services.resume_intelligence import extract_resume_profile

        await extract_resume_profile(db, source.id)

    await db.commit()
    await db.refresh(source)
    logger.info("ingest_text_source: document_id=%s source_type=%s chunks=%s", document_id, source_type, len(chunk_results))
    return str(source.id)


async def ingest_resume_pdf(
    db: AsyncSession,
    document_id: uuid.UUID,
    s3_key: str,
    original_filename: str,
) -> str:
    """
    Ingest resume PDF from storage. Extract, chunk, embed, store.
    Returns source_id as string.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise ValueError("Document not found")

    storage = get_storage()
    pdf_bytes = storage.download(s3_key)
    page_texts = _extract_text_per_page(pdf_bytes)
    if not page_texts:
        raise ValueError("No text extracted from PDF")

    page_texts_norm = [(i, t) for i, t in page_texts if t.strip()]

    chunk_results = chunk_pages(
        page_texts_norm,
        min_chars=settings.min_chunk_chars,
        max_chunks=min(50, settings.max_chunks_per_doc),
    )
    if not chunk_results:
        raise ValueError("No chunks produced")

    texts = [c.content for c in chunk_results]
    embeddings = _create_embeddings(texts)
    if len(embeddings) != len(chunk_results):
        raise ValueError("Embedding count mismatch")

    source = InterviewSource(
        document_id=document_id,
        source_type="resume",
        title=(original_filename or "Resume").replace(".pdf", "")[:200],
        original_file_name=original_filename,
    )
    db.add(source)
    await db.flush()

    for i, (cr, emb) in enumerate(zip(chunk_results, embeddings)):
        chunk = DocumentChunk(
            document_id=document_id,
            source_id=source.id,
            chunk_index=i,
            content=cr.content,
            page_number=cr.page_number,
            section=cr.section_type,
            is_boilerplate=False,
            quality_score=cr.quality_score,
            is_low_signal=cr.is_low_signal,
            content_hash=cr.content_hash,
            section_type=cr.section_type,
            doc_domain="general",
            skills_detected=cr.skills_detected,
            embedding=emb,
        )
        db.add(chunk)

    from app.services.resume_intelligence import extract_resume_profile

    await extract_resume_profile(db, source.id)

    try:
        storage.delete(s3_key)
    except Exception:
        pass

    await db.commit()
    await db.refresh(source)
    logger.info("ingest_resume_pdf: document_id=%s chunks=%s", document_id, len(chunk_results))
    return str(source.id)


def fetch_url_content(url: str) -> str:
    """Fetch URL and extract text content. Raises on error."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "InterviewOS/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    raw = raw[:MAX_URL_FETCH_CHARS]
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_TEXT_CHARS] if text else ""
