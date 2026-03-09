"""Tests for cached resume helper profile extraction."""

import uuid

import pytest


@pytest.mark.asyncio
async def test_extract_resume_profile_persists_chunk_references():
    """Resume helper profile is derived from chunks and keeps chunk-level evidence refs."""
    from app.db.base import async_session_maker
    from app.models import Document, DocumentChunk, InterviewSource, User
    from app.services.resume_intelligence import extract_resume_profile

    dim = 1536
    mock_vec = [0.1] * dim
    user_id = uuid.uuid4()

    async with async_session_maker() as db:
        db.add(User(id=user_id, email="resume-profile@t.local"))
        await db.commit()

    async with async_session_maker() as db:
        doc = Document(
            user_id=user_id,
            filename="Resume.pdf",
            s3_key="resume",
            status="ready",
            doc_domain="user_resume",
        )
        db.add(doc)
        await db.flush()

        source = InterviewSource(
            document_id=doc.id,
            source_type="resume",
            title="Resume",
            original_file_name="Resume.pdf",
        )
        db.add(source)
        await db.flush()

        chunk = DocumentChunk(
            document_id=doc.id,
            source_id=source.id,
            chunk_index=0,
            content="Python developer with AWS Certified background and 5 years of experience. Bachelor's degree in CS.",
            page_number=1,
            section_type="other",
            doc_domain="general",
            embedding=mock_vec,
            skills_detected=["python", "aws"],
        )
        db.add(chunk)
        await db.commit()

        profile = await extract_resume_profile(db, source.id)
        await db.commit()

        assert profile is not None
        assert any(item["label"].lower() == "python" for item in profile["skills"])
        assert any(item["label"].lower() == "aws" for item in profile["cloudPlatforms"])
        assert profile["experienceClaims"][0]["years"] == 5
        assert any("Bachelor" in item["label"] for item in profile["education"])
        assert profile["skills"][0]["evidence"][0]["chunkId"] == str(chunk.id)

    async with async_session_maker() as db:
        refreshed = await db.get(InterviewSource, source.id)
        assert refreshed is not None
        assert isinstance(refreshed.profile_json, dict)
        assert refreshed.profile_json["skills"][0]["evidence"][0]["chunkId"] == str(chunk.id)
