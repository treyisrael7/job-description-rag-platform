"""Evaluation quota service and interview evaluate limits."""

import uuid

import pytest

from app.core.config import settings
from app.services.evaluation_usage import evaluation_limit_for_plan


def test_evaluation_limit_for_plan() -> None:
    assert evaluation_limit_for_plan("free") == settings.plan_limit_free
    assert evaluation_limit_for_plan("pro") == settings.plan_limit_pro
    assert evaluation_limit_for_plan("enterprise") == settings.plan_limit_enterprise
    assert evaluation_limit_for_plan("unknown") == settings.plan_limit_free


@pytest.mark.asyncio
async def test_interview_evaluate_returns_429_when_monthly_quota_exceeded(
    client, demo_key_off, monkeypatch, force_auth
):
    """Second evaluate in the same month returns 429 when plan limit is 1."""
    from app.db.base import async_session_maker
    from app.models import Document, InterviewQuestion, InterviewSession, User

    monkeypatch.setattr(settings, "plan_limit_free", 1)

    async def _mock_evaluate(*args, **kwargs):
        return {
            "score": 7.0,
            "summary": "ok",
            "score_reasoning": "ok",
            "strengths": [],
            "gaps": [],
            "citations": [],
            "strengths_cited": [],
            "gaps_cited": [],
            "improved_answer": "",
            "follow_up_questions": [],
            "evidence_used": [],
            "evidence_for_scoring": [{"snippet": "x"}],
        }

    monkeypatch.setattr("app.routers.interview.generate_evaluate.evaluate_answer_with_retrieval", _mock_evaluate)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    user_id = uuid.uuid4()
    async with async_session_maker() as db:
        user = User(id=user_id, email="quota-test@t.local")
        db.add(user)
        await db.commit()
    await force_auth(user_id=user_id, email="quota-test@t.local")

    async with async_session_maker() as db:
        doc = Document(
            user_id=user_id,
            filename="jd.pdf",
            s3_key="x",
            status="ready",
            doc_domain="job_description",
        )
        db.add(doc)
        await db.flush()
        doc_id = doc.id
        session = InterviewSession(
            user_id=user_id,
            document_id=doc_id,
            mode="technical",
            difficulty="junior",
        )
        db.add(session)
        await db.flush()
        q = InterviewQuestion(
            session_id=session.id,
            type="technical",
            question="Q?",
            rubric_json={
                "bullets": ["x"],
                "evidence": [{"chunk_id": "aa", "page_number": 1, "snippet": "y"}],
                "key_topics": [],
            },
        )
        db.add(q)
        await db.flush()
        question_id = q.id
        await db.commit()

    body = {
        "document_id": str(doc_id),
        "question_id": str(question_id),
        "answer_text": "answer",
    }
    r1 = await client.post("/interview/evaluate", json=body)
    assert r1.status_code == 200
    assert r1.json()["usage"]["evaluations_used_this_month"] == 1

    r2 = await client.post("/interview/evaluate", json=body)
    assert r2.status_code == 429
    assert "limit" in (r2.json().get("detail") or "").lower()
