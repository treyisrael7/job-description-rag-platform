"""Small request-size guardrails for LLM-backed endpoints."""

from fastapi import HTTPException


def enforce_text_limit(value: str, *, field_name: str, max_chars: int) -> str:
    """Return stripped text or reject text that can drive excessive LLM cost."""
    text = value.strip()
    if len(text) > max_chars:
        raise HTTPException(
            status_code=413,
            detail={
                "error": f"{field_name} is too long",
                "field": field_name,
                "max_chars": max_chars,
                "received_chars": len(text),
            },
        )
    return text
