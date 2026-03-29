"""PDF page counting for upload limits (PyMuPDF)."""

from __future__ import annotations


def pdf_page_count(pdf_bytes: bytes) -> int:
    """Return total page count in the PDF (physical pages)."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return len(doc)
    finally:
        doc.close()
