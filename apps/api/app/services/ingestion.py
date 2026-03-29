"""Document ingestion: PDF extraction, chunking, embeddings."""

import asyncio
import logging
import uuid

from sqlalchemy import delete, func, select

from app.core.config import settings
from app.models import Document, DocumentChunk, InterviewSource
from app.services.chunking import chunk_pages
from app.services.doc_domain import detect_doc_domain
from app.services.jd_chunking import chunk_jd_pages
from app.services.jd_extraction import extract_jd_struct
from app.services.jd_sections import normalize_jd_text
from app.services.role_intelligence import infer_role_profile
from app.services.pdf_pages import pdf_page_count
from app.services.storage import get_storage

logger = logging.getLogger(__name__)


def _extract_text_per_page(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Extract text per page using PyMuPDF. Returns [(page_number, text), ...]."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        result = []
        limit = min(len(doc), settings.max_pdf_pages)
        for i in range(limit):
            page = doc[i]
            text = page.get_text(sort=True)
            result.append((i + 1, text))
            logger.debug(
                "PDF extraction page=%s text_len=%s",
                i + 1,
                len(text),
            )
        logger.info(
            "PDF extraction done: pages_extracted=%s per_page_lengths=%s",
            len(result),
            [len(t) for _, t in result],
        )
        return result
    finally:
        doc.close()


def _create_embeddings(texts: list[str]) -> list[list[float]]:
    """Create embeddings via OpenAI API. Returns list of embedding vectors."""
    from openai import OpenAI

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    client = OpenAI(api_key=settings.openai_api_key)

    # text-embedding-3 models support dimensions param; older models do not
    create_kwargs: dict = {
        "input": texts,
        "model": settings.openai_embedding_model,
    }
    if settings.openai_embedding_model.startswith("text-embedding-3"):
        create_kwargs["dimensions"] = settings.openai_embedding_dim
    response = client.embeddings.create(**create_kwargs)

    # Preserve order; response.data is in order of input
    by_index = {item.index: item.embedding for item in response.data}
    return [by_index[i] for i in range(len(texts))]


async def run_ingestion(document_id: uuid.UUID) -> None:
    """
    Ingestion flow: Upload job description PDF → extract text → chunk/index → inferRoleProfile → save.

    Order: extract text → chunk (job description or general) → infer_role_profile(jdText) → save role_profile
    on document → create embeddings → store chunks. roleProfile is used by Interview Setup
    for domain-aware question generation + RAG evidence.
    On success: update document page_count, status=ready, role_profile.
    On failure: update status=failed and error_message.
    """
    from app.db.base import async_session_maker

    async with async_session_maker() as db:
        try:
            result = await db.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = result.scalar_one_or_none()
            if not doc:
                return

            storage = get_storage()
            pdf_bytes = storage.download(doc.s3_key)

            total_pages = pdf_page_count(pdf_bytes)
            if total_pages > settings.max_pdf_pages:
                doc.status = "failed"
                doc.error_message = (
                    f"PDF has {total_pages} pages; maximum allowed is {settings.max_pdf_pages}. "
                    "Please upload a shorter document."
                )
                await db.commit()
                return

            page_texts = _extract_text_per_page(pdf_bytes)
            if not page_texts:
                doc.status = "failed"
                doc.error_message = "No text extracted from PDF"
                await db.commit()
                return

            full_text = "\n\n".join(t for _, t in page_texts)
            norm_text = normalize_jd_text(full_text)

            # Auto-detect doc_domain: job_description if >=2 job description signals, else general
            doc_domain = detect_doc_domain(full_text)
            doc.doc_domain = doc_domain

            chunk_stats: dict = {}
            if doc_domain == "job_description":
                jd_struct = extract_jd_struct(norm_text)
                doc.jd_extraction_json = jd_struct
                chunk_results = chunk_jd_pages(
                    page_texts,
                    min_chars=settings.min_chunk_chars,
                    max_chunks=settings.max_chunks_per_doc,
                )
            else:
                chunk_results = chunk_pages(
                    page_texts,
                    min_chars=settings.min_chunk_chars,
                    max_chunks=settings.max_chunks_per_doc,
                    stats=chunk_stats,
                )
            chunk_stats.setdefault("chunks_produced", len(chunk_results))
            chunk_stats.setdefault("total_paragraphs", 0)

            # Role Intelligence: infer profile after extraction/chunking
            doc.role_profile = infer_role_profile(full_text)

            if not chunk_results:
                doc.status = "failed"
                doc.error_message = "No chunks produced after extraction"
                await db.commit()
                return

            low_signal_count = sum(1 for c in chunk_results if c.is_low_signal)

            logger.info(
                "ingestion BEFORE insert: pages_extracted=%s num_paragraphs=%s num_chunks_generated=%s "
                "num_chunks_marked_low_signal=%s num_chunks_to_insert=%s",
                len(page_texts),
                chunk_stats.get("total_paragraphs", "?"),
                chunk_stats.get("chunks_produced", len(chunk_results)),
                low_signal_count,
                len(chunk_results),
            )

            texts = [c.content for c in chunk_results]
            embeddings = _create_embeddings(texts)

            if len(embeddings) != len(chunk_results):
                logger.error(
                    "embedding count mismatch: chunks=%s embeddings=%s",
                    len(chunk_results),
                    len(embeddings),
                )
                doc.status = "failed"
                doc.error_message = f"Embedding count mismatch: {len(embeddings)} != {len(chunk_results)}"
                await db.commit()
                return

            await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))

            # Get or create JD source for this document (Interview Kit)
            source_result = await db.execute(
                select(InterviewSource).where(
                    InterviewSource.document_id == document_id,
                    InterviewSource.source_type == "jd",
                )
            )
            source = source_result.scalar_one_or_none()
            if not source:
                source = InterviewSource(
                    document_id=document_id,
                    source_type="jd",
                    title=doc.filename or "Job Description",
                    original_file_name=doc.filename,
                )
                db.add(source)
                await db.flush()

            inserted = 0
            for i, (cr, embedding) in enumerate(zip(chunk_results, embeddings)):
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
                    skills_detected=cr.skills_detected,
                    doc_domain=cr.doc_domain,
                    embedding=embedding,
                )
                db.add(chunk)
                inserted += 1

            logger.info(
                "ingestion AFTER insert: num_rows_inserted=%s document_id=%s",
                inserted,
                document_id,
            )
            doc.page_count = len(page_texts)
            doc.status = "ready"
            doc.error_message = None
            await db.commit()

            count_result = await db.execute(
                select(func.count()).select_from(DocumentChunk).where(
                    DocumentChunk.document_id == document_id
                )
            )
            num_rows_in_db = count_result.scalar() or 0
            logger.info(
                "ingestion AFTER commit: num_rows_in_db=%s (inserted=%s) document_id=%s",
                num_rows_in_db,
                inserted,
                document_id,
            )
            if num_rows_in_db != inserted:
                logger.warning(
                    "ingestion row count mismatch: inserted=%s but DB has %s",
                    inserted,
                    num_rows_in_db,
                )

            # Competency Map extraction (JD only): RAG-based, runs after chunks are ready
            if doc_domain == "job_description":
                try:
                    from app.services.competency_extraction import extract_competencies

                    comps = await extract_competencies(db, document_id)
                    if comps is not None:
                        result = await db.execute(
                            select(Document).where(Document.id == document_id)
                        )
                        doc_for_update = result.scalar_one_or_none()
                        if doc_for_update:
                            doc_for_update.competencies = comps
                            await db.commit()
                            logger.info(
                                "Competency extraction: stored %s competencies document_id=%s",
                                len(comps),
                                document_id,
                            )
                    else:
                        logger.info(
                            "Competency extraction: skipped or failed document_id=%s",
                            document_id,
                        )
                except Exception as comp_err:
                    logger.warning(
                        "Competency extraction failed (non-fatal): %s document_id=%s",
                        comp_err,
                        document_id,
                        exc_info=True,
                    )
                    # Do not fail ingestion; competencies can be re-run later

                try:
                    from app.services.rubric_extractor import extract_rubric_from_jd

                    rubric = await asyncio.to_thread(extract_rubric_from_jd, norm_text)
                    if rubric:
                        result = await db.execute(
                            select(Document).where(Document.id == document_id)
                        )
                        doc_for_rubric = result.scalar_one_or_none()
                        if doc_for_rubric:
                            doc_for_rubric.rubric_json = rubric
                            await db.commit()
                            logger.info(
                                "Rubric extraction: stored %s dimensions document_id=%s",
                                len(rubric),
                                document_id,
                            )
                    else:
                        logger.info(
                            "Rubric extraction: empty or skipped document_id=%s",
                            document_id,
                        )
                except Exception as rubric_err:
                    logger.warning(
                        "Rubric extraction failed (non-fatal): %s document_id=%s",
                        rubric_err,
                        document_id,
                        exc_info=True,
                    )

        except Exception as e:
            await db.rollback()
            # Use fresh session to persist failure status
            async with async_session_maker() as db2:
                result = await db2.execute(
                    select(Document).where(Document.id == document_id)
                )
                doc = result.scalar_one_or_none()
                if doc:
                    doc.status = "failed"
                    doc.error_message = str(e)[:2000]  # Cap error length
                await db2.commit()
