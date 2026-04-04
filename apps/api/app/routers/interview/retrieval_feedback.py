"""POST /interview/retrieval-feedback — user-reported retrieval quality for an evaluation."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import assert_resource_ownership, get_current_user
from app.db.session import get_db
from app.models import (
    Document,
    InterviewAnswer,
    InterviewQuestion,
    InterviewRetrievalFeedback,
    InterviewSession,
    User,
)
from app.routers.interview.router import router
from app.routers.interview.schemas import (
    InterviewRetrievalFeedbackInput,
    InterviewRetrievalFeedbackOutput,
)


def _chunk_ids_from_stored_feedback(fb: dict[str, Any]) -> list[str]:
    """Best-effort extraction of chunk ids the evaluator surfaced (evidence + citations)."""
    ordered: list[str] = []
    taken: set[str] = set()

    def _take(cid: object) -> None:
        if cid is None:
            return
        s = str(cid).strip()
        if not s or s in taken:
            return
        taken.add(s)
        ordered.append(s)

    for item in fb.get("evidence_used") or []:
        if isinstance(item, dict):
            _take(item.get("chunkId") or item.get("chunk_id"))

    for c in fb.get("citations") or []:
        if isinstance(c, dict):
            _take(c.get("chunk_id") or c.get("chunkId"))

    for bucket in ("strengths_cited", "gaps_cited"):
        for item in fb.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            for cit in item.get("citations") or []:
                if isinstance(cit, dict):
                    _take(cit.get("chunkId") or cit.get("chunk_id"))

    return ordered


@router.post("/retrieval-feedback", response_model=InterviewRetrievalFeedbackOutput)
async def submit_retrieval_feedback(
    body: InterviewRetrievalFeedbackInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Record that retrieval / cited evidence for a completed evaluation felt wrong.
    Stores document_id, question_id, answer_id, and a snapshot of chunk ids for RAG tuning.
    """
    result = await db.execute(
        select(InterviewAnswer, InterviewQuestion, InterviewSession)
        .join(InterviewQuestion, InterviewAnswer.question_id == InterviewQuestion.id)
        .join(InterviewSession, InterviewQuestion.session_id == InterviewSession.id)
        .where(InterviewAnswer.id == body.answer_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Answer not found")

    answer, question, session = row[0], row[1], row[2]

    if session.document_id != body.document_id:
        raise HTTPException(status_code=400, detail="document_id does not match this answer")

    doc_result = await db.execute(select(Document).where(Document.id == body.document_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    assert_resource_ownership(session, current_user)

    chunk_ids = body.retrieval_chunk_ids
    if chunk_ids is None:
        chunk_ids = _chunk_ids_from_stored_feedback(answer.feedback_json)

    existing = await db.execute(
        select(InterviewRetrievalFeedback).where(InterviewRetrievalFeedback.answer_id == answer.id)
    )
    prior = existing.scalar_one_or_none()

    if prior:
        prior.reason = body.reason
        prior.retrieval_chunk_ids = chunk_ids
        await db.commit()
        await db.refresh(prior)
        return InterviewRetrievalFeedbackOutput(id=prior.id, updated=True)

    fb_row = InterviewRetrievalFeedback(
        user_id=current_user.id,
        document_id=body.document_id,
        session_id=session.id,
        question_id=question.id,
        answer_id=answer.id,
        retrieval_chunk_ids=chunk_ids,
        reason=body.reason,
    )
    db.add(fb_row)
    await db.commit()
    await db.refresh(fb_row)
    return InterviewRetrievalFeedbackOutput(id=fb_row.id, updated=False)
