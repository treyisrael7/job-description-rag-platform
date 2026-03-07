#!/usr/bin/env python3
"""JD ingestion stats: total_chunks, low_signal, embedded, pages, section_type breakdown. Fallback when API unavailable."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))


async def main():
    from sqlalchemy import text
    from app.db.base import async_session_maker

    doc_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not doc_id:
        last_file = Path(__file__).parent / ".last-document-id"
        if last_file.exists():
            doc_id = last_file.read_text().strip()
    if not doc_id:
        print("Usage: python scripts/chunk-stats.py [doc_id]")
        print("Or run test-upload.ps1 first to create .last-document-id")
        sys.exit(1)

    async with async_session_maker() as session:
        r = await session.execute(
            text("""
                SELECT
                    COUNT(*),
                    COALESCE(SUM(CASE WHEN is_low_signal THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END), 0),
                    COUNT(DISTINCT page_number),
                    COALESCE(ROUND(AVG(LENGTH(content)))::int, 0),
                    COALESCE(MIN(LENGTH(content)), 0),
                    COALESCE(MAX(LENGTH(content)), 0)
                FROM document_chunks WHERE document_id = :doc_id
            """),
            {"doc_id": doc_id},
        )
        row = r.fetchone()
        # Section-type breakdown for JDs
        section_r = await session.execute(
            text("""
                SELECT section_type, COUNT(*) FROM document_chunks
                WHERE document_id = :doc_id AND section_type IS NOT NULL
                GROUP BY section_type
            """),
            {"doc_id": doc_id},
        )
        section_breakdown = {str(sr[0]): sr[1] for sr in section_r}

    if not row or row[0] == 0:
        print("No chunks found for document.")
        sys.exit(1)

    total, low_signal, embedded, pages, avg_len, min_len, max_len = row
    print(f"total_chunks:      {total}")
    print(f"low_signal_chunks: {low_signal}")
    print(f"embedded_chunks:   {embedded}")
    print(f"pages_covered:     {pages}")
    print(f"avg_chunk_length:  {avg_len}")
    print(f"min_chunk_length:  {min_len}")
    print(f"max_chunk_length:  {max_len}")
    if section_breakdown:
        print("section_type_breakdown:")
        for k, v in section_breakdown.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
