"""Integration tests: built-in retrieval eval dataset against a real Postgres corpus.

Runs the same retrieval stack as production (semantic / hybrid / keyword) with a
deterministic query embedding so CI does not require OPENAI_API_KEY.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import delete, select

from app.db.base import async_session_maker
from app.models import Document, DocumentChunk, InterviewSource, User
from app.models.document_chunk import EMBEDDING_DIM
from evals.retrieval.ci_constants import (
    CI_SHARED_EMBEDDING_VALUE,
    PLATFORM_ENGINEER_JD_DOCUMENT_ID,
    PLATFORM_ENGINEER_JD_FIXTURE_REF,
    PLATFORM_ENGINEER_JD_USER_ID,
)
from evals.retrieval.loader import load_builtin_dataset
from evals.retrieval.runner import run_eval_dataset_for_modes


def _shared_embedding() -> list[float]:
    return [CI_SHARED_EMBEDDING_VALUE] * EMBEDDING_DIM


# Corpus aligned with evals/retrieval/cases/job_description_starter.json (JD + resume kit).
# top_k in the dataset is 10 so MMR returns the full candidate pool (<=10 chunks).
_CI_SOURCES: list[dict] = [
    {
        "source_type": "jd",
        "title": "Platform Engineer JD (CI)",
        "original_file_name": "platform_engineer_ci.pdf",
        "chunks": [
            {
                "chunk_index": 0,
                "page_number": 1,
                "section_type": "compensation",
                "content": (
                    "The salary range for this senior role is $160,000 to $190,000 annually. "
                    "We offer a competitive salary range and equity."
                ),
            },
            {
                "chunk_index": 1,
                "page_number": 1,
                "section_type": "qualifications",
                "content": (
                    "Education requirements: a Bachelor's degree in Computer Science or a related "
                    "field is required. Qualifications and required skills: Python and PostgreSQL "
                    "expertise with 5+ years building distributed systems for production backends."
                ),
            },
            {
                "chunk_index": 2,
                "page_number": 2,
                "section_type": "tools",
                "content": (
                    "Skills and qualifications for tooling are required: tools and technologies "
                    "include AWS, Kubernetes, Terraform, and pgvector. The team uses Python "
                    "services across the platform."
                ),
            },
            {
                "chunk_index": 3,
                "page_number": 2,
                "section_type": "responsibilities",
                "content": (
                    "Main responsibilities: you will build and operate backend services and "
                    "collaborate with product, data, and infrastructure partners in this role."
                ),
            },
            {
                "chunk_index": 4,
                "page_number": 3,
                "section_type": "compensation",
                "content": (
                    "Compensation detail (tabular layout): base pay band in USD is summarized below. "
                    "| Role | Base Pay (USD) | | Senior Platform Engineer | $160,000 - $190,000 | "
                    "Annual figures; bonus eligible."
                ),
            },
            {
                "chunk_index": 5,
                "page_number": 3,
                "section_type": "about",
                "content": (
                    "Remote work policy: we are hybrid with core collaboration days; "
                    "remote-first Fridays. Expect Tuesday through Thursday in the office "
                    "for synchronous planning."
                ),
            },
            {
                "chunk_index": 6,
                "page_number": 3,
                "section_type": "about",
                "content": (
                    "Reporting structure: this role reports to the Engineering Manager leading "
                    "the Platform reliability group. Close partnership with the Platform team "
                    "is expected."
                ),
            },
        ],
    },
    {
        "source_type": "resume",
        "title": "Candidate Resume (CI)",
        "original_file_name": "resume_ci.pdf",
        "chunks": [
            {
                "chunk_index": 0,
                "page_number": 1,
                "section_type": "summary",
                "doc_domain": "resume",
                "content": (
                    "Resume highlights — leadership experience listed here: previously an Engineering "
                    "Lead managing a team of six engineers on observability and incident programs. "
                    "This resume section summarizes leadership experience for interview follow-ups."
                ),
            },
        ],
    },
]


async def _teardown_ci_retrieval_fixture() -> None:
    async with async_session_maker() as db:
        await db.execute(delete(Document).where(Document.id == PLATFORM_ENGINEER_JD_DOCUMENT_ID))
        await db.execute(delete(User).where(User.id == PLATFORM_ENGINEER_JD_USER_ID))
        await db.commit()


async def _seed_ci_fixture_document() -> None:
    emb = _shared_embedding()
    async with async_session_maker() as db:
        await db.execute(delete(Document).where(Document.id == PLATFORM_ENGINEER_JD_DOCUMENT_ID))
        result = await db.execute(select(User).where(User.id == PLATFORM_ENGINEER_JD_USER_ID))
        if result.scalar_one_or_none() is None:
            db.add(
                User(
                    id=PLATFORM_ENGINEER_JD_USER_ID,
                    email="retrieval-eval-ci@fixture.local",
                    clerk_id=None,
                )
            )
        await db.commit()

    async with async_session_maker() as db:
        doc = Document(
            id=PLATFORM_ENGINEER_JD_DOCUMENT_ID,
            user_id=PLATFORM_ENGINEER_JD_USER_ID,
            filename="platform_engineer_ci.pdf",
            s3_key="retrieval-eval/ci/platform_engineer_ci.pdf",
            status="ready",
            doc_domain="job_description",
        )
        db.add(doc)
        await db.flush()

        for src_spec in _CI_SOURCES:
            source = InterviewSource(
                document_id=doc.id,
                source_type=src_spec["source_type"],
                title=src_spec["title"],
                original_file_name=src_spec["original_file_name"],
            )
            db.add(source)
            await db.flush()
            for ch in src_spec["chunks"]:
                db.add(
                    DocumentChunk(
                        document_id=doc.id,
                        source_id=source.id,
                        chunk_index=ch["chunk_index"],
                        content=ch["content"],
                        page_number=ch["page_number"],
                        section_type=ch["section_type"],
                        doc_domain=ch.get("doc_domain", "job_description"),
                        embedding=emb,
                    )
                )
        await db.commit()


@pytest.mark.asyncio
async def test_job_description_starter_passes_all_modes(monkeypatch):
    """Built-in dataset should pass semantic, hybrid, and keyword against the seeded corpus."""
    await _seed_ci_fixture_document()
    try:
        monkeypatch.setattr("evals.retrieval.runner.embed_query", lambda _query: _shared_embedding())

        async def _resolve_fixture(name: str) -> UUID:
            assert name == PLATFORM_ENGINEER_JD_FIXTURE_REF
            return PLATFORM_ENGINEER_JD_DOCUMENT_ID

        dataset = load_builtin_dataset("job_description_starter")
        async with async_session_maker() as db:
            runs = await run_eval_dataset_for_modes(
                db=db,
                dataset=dataset,
                modes=("semantic", "hybrid", "keyword"),
                fixture_resolver=_resolve_fixture,
            )

        assert [r.mode for r in runs] == ["semantic", "hybrid", "keyword"]
        for run in runs:
            assert run.failed_cases == 0, (
                f"mode={run.mode} failures={run.failed_cases} "
                f"details={[r for r in run.results if not r.passed]}"
            )
            assert run.passed_cases == run.total_cases == len(dataset.cases)

        async with async_session_maker() as db:
            row = await db.execute(select(Document).where(Document.id == PLATFORM_ENGINEER_JD_DOCUMENT_ID))
            assert row.scalar_one_or_none() is not None
    finally:
        await _teardown_ci_retrieval_fixture()
