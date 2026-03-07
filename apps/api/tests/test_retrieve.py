"""Tests for POST /retrieve endpoint."""

import uuid

import pytest

from app.core.config import settings


@pytest.fixture
def demo_key_off(monkeypatch):
    monkeypatch.setattr(settings, "demo_key", None)


@pytest.mark.asyncio
async def test_retrieve_requires_valid_input(client, demo_key_off):
    """Retrieve returns 422 for missing or invalid body."""
    resp = await client.post("/retrieve", json={})
    assert resp.status_code == 422

    resp = await client.post(
        "/retrieve",
        json={
            "user_id": "11111111-1111-1111-1111-111111111111",
            "document_id": "11111111-1111-1111-1111-111111111111",
            "query": "",  # min_length=1
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_retrieve_document_not_found(client, demo_key_off):
    """Retrieve returns 404 for unknown document."""
    resp = await client.post(
        "/retrieve",
        json={
            "user_id": "11111111-1111-1111-1111-111111111111",
            "document_id": "11111111-1111-1111-1111-111111111111",
            "query": "test query",
            "top_k": 3,
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retrieve_rejects_top_k_exceeds_max(client, demo_key_off, monkeypatch):
    """Retrieve returns 400 when top_k > TOP_K_MAX."""
    from app.db.base import async_session_maker
    from app.models import Document, User

    monkeypatch.setattr(settings, "top_k_max", 5)

    user_id = uuid.uuid4()
    async with async_session_maker() as db:
        user = User(id=user_id, email="retrieve-test@t.local")
        db.add(user)
        await db.commit()
    async with async_session_maker() as db:
        doc = Document(
            user_id=user_id,
            filename="x.pdf",
            s3_key="x",
            status="ready",
        )
        db.add(doc)
        await db.flush()
        doc_id = doc.id
        await db.commit()

    resp = await client.post(
        "/retrieve",
        json={
            "user_id": str(user_id),
            "document_id": str(doc_id),
            "query": "test",
            "top_k": 6,  # > top_k_max (5), but <= Pydantic le=8 so we hit the handler
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "top_k exceeds limit"
    assert resp.json()["detail"]["max"] == 5


@pytest.mark.asyncio
async def test_retrieve_rejects_document_not_ready(client, demo_key_off):
    """Retrieve returns 400 when document status is not ready."""
    from app.db.base import async_session_maker
    from app.models import Document, User

    user_id = uuid.uuid4()
    async with async_session_maker() as db:
        user = User(id=user_id, email="retrieve-test2@t.local")
        db.add(user)
        await db.commit()
    async with async_session_maker() as db:
        doc = Document(
            user_id=user_id,
            filename="x.pdf",
            s3_key="x",
            status="uploaded",
        )
        db.add(doc)
        await db.flush()
        doc_id = doc.id
        await db.commit()

    resp = await client.post(
        "/retrieve",
        json={
            "user_id": str(user_id),
            "document_id": str(doc_id),
            "query": "test",
            "top_k": 3,
        },
    )
    assert resp.status_code == 400
    assert "ready" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_retrieve_success_returns_chunks(client, demo_key_off, monkeypatch):
    """Retrieve returns metadata-rich chunks: text, score, sourceType, sourceTitle, page, chunkId."""
    from app.db.base import async_session_maker
    from app.models import Document, DocumentChunk, InterviewSource, User

    # Deterministic embedding: same vector for query and chunk -> cosine sim 1.0
    dim = 1536
    mock_vec = [0.1] * dim

    def _mock_embed(q: str):
        return mock_vec

    monkeypatch.setattr("app.services.retrieval.embed_query", _mock_embed)
    monkeypatch.setattr("app.routers.retrieve.embed_query", _mock_embed)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    user_id = uuid.uuid4()
    async with async_session_maker() as db:
        user = User(id=user_id, email="retrieve-success@t.local")
        db.add(user)
        await db.commit()
    async with async_session_maker() as db:
        doc = Document(
            user_id=user_id,
            filename="x.pdf",
            s3_key="x",
            status="ready",
        )
        db.add(doc)
        await db.flush()
        doc_id = doc.id
        source = InterviewSource(
            document_id=doc_id,
            source_type="jd",
            title="x.pdf",
            original_file_name="x.pdf",
        )
        db.add(source)
        await db.flush()
        chunk = DocumentChunk(
            document_id=doc_id,
            source_id=source.id,
            chunk_index=0,
            content="Machine learning skills include Python and TensorFlow.",
            page_number=1,
            section_type="other",
            doc_domain="general",
            embedding=mock_vec,
        )
        db.add(chunk)
        await db.flush()
        chunk_id = chunk.id
        await db.commit()

    resp = await client.post(
        "/retrieve",
        json={
            "user_id": str(user_id),
            "document_id": str(doc_id),
            "query": "machine learning",
            "top_k": 3,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "chunks" in data
    assert len(data["chunks"]) >= 1
    c = data["chunks"][0]
    assert c["chunkId"] == str(chunk_id)
    assert c["page"] == 1
    assert "Machine learning" in c["text"]
    assert c["sourceType"] == "jd"
    assert c["sourceTitle"] == "x.pdf"
    assert c["score"] == pytest.approx(1.0, abs=1e-4)
    assert c["is_low_signal"] is False


@pytest.mark.asyncio
async def test_retrieve_returns_section_type_for_jd_doc(client, demo_key_off, monkeypatch):
    """Retrieve returns section_type in chunks when doc has doc_domain=job_description."""
    from app.db.base import async_session_maker
    from app.models import Document, DocumentChunk, InterviewSource, User

    dim = 1536
    mock_vec = [0.1] * dim

    def _mock_embed(q: str):
        return mock_vec

    monkeypatch.setattr("app.services.retrieval.embed_query", _mock_embed)
    monkeypatch.setattr("app.routers.retrieve.embed_query", _mock_embed)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    user_id = uuid.uuid4()
    async with async_session_maker() as db:
        user = User(id=user_id, email="jd-retrieve@t.local")
        db.add(user)
        await db.commit()
    async with async_session_maker() as db:
        doc = Document(
            user_id=user_id,
            filename="jd.pdf",
            s3_key="x",
            status="ready",
            doc_domain="job_description",
            jd_extraction_json={"role_title": "AI Engineer", "company": "Acme"},
        )
        db.add(doc)
        await db.flush()
        doc_id = doc.id
        source = InterviewSource(
            document_id=doc_id,
            source_type="jd",
            title="jd.pdf",
            original_file_name="jd.pdf",
        )
        db.add(source)
        await db.flush()
        chunk = DocumentChunk(
            document_id=doc_id,
            source_id=source.id,
            chunk_index=0,
            content="Python, TensorFlow, AWS required. 5+ years experience.",
            page_number=1,
            section_type="qualifications",
            doc_domain="job_description",
            embedding=mock_vec,
        )
        db.add(chunk)
        await db.flush()
        chunk_id = chunk.id
        await db.commit()

    resp = await client.post(
        "/retrieve",
        json={
            "user_id": str(user_id),
            "document_id": str(doc_id),
            "query": "what skills are required?",
            "top_k": 3,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["chunks"]) >= 1
    c = data["chunks"][0]
    assert c["section_type"] == "qualifications"


@pytest.mark.asyncio
async def test_retrieve_section_types_filter(client, demo_key_off, monkeypatch):
    """Retrieve respects optional section_types filter."""
    from app.db.base import async_session_maker
    from app.models import Document, DocumentChunk, InterviewSource, User

    dim = 1536
    mock_vec = [0.1] * dim

    def _mock_embed(q: str):
        return mock_vec

    monkeypatch.setattr("app.services.retrieval.embed_query", _mock_embed)
    monkeypatch.setattr("app.routers.retrieve.embed_query", _mock_embed)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    user_id = uuid.uuid4()
    async with async_session_maker() as db:
        user = User(id=user_id, email="filter-test@t.local")
        db.add(user)
        await db.commit()
    async with async_session_maker() as db:
        doc = Document(
            user_id=user_id,
            filename="x.pdf",
            s3_key="x",
            status="ready",
            doc_domain="job_description",
        )
        db.add(doc)
        await db.flush()
        doc_id = doc.id
        source = InterviewSource(
            document_id=doc_id,
            source_type="jd",
            title="x.pdf",
            original_file_name="x.pdf",
        )
        db.add(source)
        await db.flush()
        for idx, st in enumerate(["qualifications", "responsibilities"]):
            chunk = DocumentChunk(
                document_id=doc_id,
                source_id=source.id,
                chunk_index=idx,
                content=f"Content for {st} section.",
                page_number=1,
                section_type=st,
                doc_domain="job_description",
                embedding=mock_vec,
            )
            db.add(chunk)
        await db.flush()
        await db.commit()

    # Filter by qualifications only - should exclude responsibilities chunk
    resp = await client.post(
        "/retrieve",
        json={
            "user_id": str(user_id),
            "document_id": str(doc_id),
            "query": "skills",
            "top_k": 5,
            "section_types": ["qualifications"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    for c in data["chunks"]:
        assert c["section_type"] == "qualifications"


@pytest.mark.asyncio
async def test_retrieve_source_types_filter(client, demo_key_off, monkeypatch):
    """Retrieve respects optional source_types filter; returns only chunks from matching sources."""
    from app.db.base import async_session_maker
    from app.models import Document, DocumentChunk, InterviewSource, User

    dim = 1536
    mock_vec = [0.1] * dim

    def _mock_embed(q: str):
        return mock_vec

    monkeypatch.setattr("app.services.retrieval.embed_query", _mock_embed)
    monkeypatch.setattr("app.routers.retrieve.embed_query", _mock_embed)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    user_id = uuid.uuid4()
    async with async_session_maker() as db:
        user = User(id=user_id, email="source-filter@t.local")
        db.add(user)
        await db.commit()
    async with async_session_maker() as db:
        doc = Document(
            user_id=user_id,
            filename="kit.pdf",
            s3_key="x",
            status="ready",
            doc_domain="job_description",
        )
        db.add(doc)
        await db.flush()
        doc_id = doc.id
        # JD source
        src_jd = InterviewSource(
            document_id=doc_id,
            source_type="jd",
            title="Job Description",
            original_file_name="jd.pdf",
        )
        db.add(src_jd)
        await db.flush()
        # Notes source
        src_notes = InterviewSource(
            document_id=doc_id,
            source_type="notes",
            title="Interview Notes",
            original_file_name=None,
        )
        db.add(src_notes)
        await db.flush()
        chunk_jd = DocumentChunk(
            document_id=doc_id,
            source_id=src_jd.id,
            chunk_index=0,
            content="Python and AWS required.",
            page_number=1,
            section_type="qualifications",
            doc_domain="job_description",
            embedding=mock_vec,
        )
        chunk_notes = DocumentChunk(
            document_id=doc_id,
            source_id=src_notes.id,
            chunk_index=0,
            content="Candidate mentioned Kubernetes experience.",
            page_number=1,
            section_type="other",
            doc_domain="general",
            embedding=mock_vec,
        )
        db.add(chunk_jd)
        db.add(chunk_notes)
        await db.commit()

    # Filter by jd only - should exclude notes chunk
    resp = await client.post(
        "/retrieve",
        json={
            "user_id": str(user_id),
            "document_id": str(doc_id),
            "query": "skills",
            "top_k": 5,
            "source_types": ["jd"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["chunks"]) >= 1
    for c in data["chunks"]:
        assert c["sourceType"] == "jd"
        assert c["sourceTitle"] == "Job Description"

    # No filter - returns chunks from all sources
    resp2 = await client.post(
        "/retrieve",
        json={
            "user_id": str(user_id),
            "document_id": str(doc_id),
            "query": "skills",
            "top_k": 5,
        },
    )
    assert resp2.status_code == 200
    types_seen = {c["sourceType"] for c in resp2.json()["chunks"]}
    assert "jd" in types_seen or "notes" in types_seen
