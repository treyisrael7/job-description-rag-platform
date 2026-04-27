"""Tests for demo gate middleware."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings


@pytest.mark.asyncio
async def test_health_public_without_key(client):
    """Health is public."""
    resp = await client.get("/health")
    assert resp.status_code in (200, 503)


@pytest.mark.asyncio
async def test_protected_route_without_demo_key(client, monkeypatch, force_auth):
    """When demo mode is off, protected routes work without x-demo-key."""
    monkeypatch.setattr(settings, "demo_mode_enabled", False)
    monkeypatch.setattr(settings, "demo_key", None)
    await force_auth()
    resp = await client.post(
        "/ask",
        json={
            "document_id": "11111111-1111-1111-1111-111111111111",
            "question": "test",
        },
    )
    # 404 = doc not found; anything but 401 means we passed the gate
    assert resp.status_code != 401


@pytest.mark.asyncio
async def test_protected_route_uses_demo_user_without_key(client, monkeypatch):
    """When demo mode is on, protected routes do not require a browser demo key."""
    monkeypatch.setattr(settings, "demo_mode_enabled", True)
    monkeypatch.setattr(settings, "demo_key", None)
    monkeypatch.setattr(settings, "clerk_jwks_url", None)
    resp = await client.post(
        "/ask",
        json={
            "document_id": "11111111-1111-1111-1111-111111111111",
            "question": "test",
        },
    )
    assert resp.status_code != 401


@pytest.mark.asyncio
async def test_protected_route_allows_missing_key(client, monkeypatch):
    """When demo mode is on, missing x-demo-key is fine."""
    monkeypatch.setattr(settings, "demo_mode_enabled", True)
    monkeypatch.setattr(settings, "demo_key", None)
    monkeypatch.setattr(settings, "clerk_jwks_url", None)
    resp = await client.post("/ask", json={})
    assert resp.status_code != 401


@pytest.mark.asyncio
async def test_protected_route_ignores_legacy_wrong_key(client, monkeypatch):
    """When demo mode is on, legacy x-demo-key values are not required."""
    monkeypatch.setattr(settings, "demo_mode_enabled", True)
    monkeypatch.setattr(settings, "demo_key", None)
    monkeypatch.setattr(settings, "clerk_jwks_url", None)
    resp = await client.post("/ask", json={}, headers={"x-demo-key": "wrong"})
    assert resp.status_code != 401


@pytest.mark.asyncio
async def test_public_paths_when_demo_key_set(client, monkeypatch):
    """When demo mode is on, public paths still work without header."""
    monkeypatch.setattr(settings, "demo_mode_enabled", True)
    monkeypatch.setattr(settings, "demo_key", None)
    for path in ["/", "/health", "/openapi.json"]:
        resp = await client.get(path)
        assert resp.status_code in (200, 503), f"{path} should be public"


@pytest.mark.asyncio
async def test_demo_mode_off_requires_real_auth(client, monkeypatch):
    """Demo headers do not enable demo auth when DEMO_MODE_ENABLED is false."""
    monkeypatch.setattr(settings, "demo_mode_enabled", False)
    monkeypatch.setattr(settings, "demo_key", "should-not-matter")
    monkeypatch.setattr(settings, "clerk_jwks_url", None)
    resp = await client.post(
        "/ask",
        json={"document_id": "11111111-1111-1111-1111-111111111111", "question": "x"},
        headers={"x-demo-key": "should-not-matter"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bearer_plus_demo_key_returns_400(client, monkeypatch):
    """Sending both Bearer and x-demo-key is rejected (middleware)."""
    monkeypatch.setattr(settings, "demo_mode_enabled", True)
    monkeypatch.setattr(settings, "demo_key", "test-secret")
    resp = await client.post(
        "/ask",
        json={"document_id": "11111111-1111-1111-1111-111111111111", "question": "x"},
        headers={
            "Authorization": "Bearer any-token",
            "x-demo-key": "test-secret",
        },
    )
    assert resp.status_code == 400
    assert "Bearer" in resp.text or "demo" in resp.text.lower()


@pytest.mark.asyncio
async def test_demo_mode_authenticates_without_clerk(client, monkeypatch):
    """Demo mode resolves sandbox user and reaches the handler without Clerk."""
    import uuid

    from app.db.base import async_session_maker
    from app.models import Document, User

    demo_uid = uuid.uuid4()
    monkeypatch.setattr(settings, "demo_user_id", demo_uid)
    monkeypatch.setattr(settings, "demo_mode_enabled", True)
    monkeypatch.setattr(settings, "demo_key", None)
    monkeypatch.setattr(settings, "clerk_jwks_url", None)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    doc_id = uuid.uuid4()
    async with async_session_maker() as db:
        db.add(User(id=demo_uid, email="demo@sandbox.local"))
        await db.commit()
    async with async_session_maker() as db:
        db.add(
            Document(
                id=doc_id,
                user_id=demo_uid,
                filename="jd.pdf",
                s3_key="x",
                status="ready",
                doc_domain="job_description",
            )
        )
        await db.commit()

    with patch("app.routers.ask.retrieve_chunks", new_callable=AsyncMock, return_value=[]):
        with patch("app.routers.ask.embed_query", return_value=[0.1] * 1536):
            resp = await client.post(
                "/ask",
                json={"document_id": str(doc_id), "question": "What is the role?"},
            )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data


@pytest.mark.asyncio
async def test_demo_sessions_are_isolated(client, monkeypatch):
    """Different anonymous demo session ids resolve to different sandbox users."""
    monkeypatch.setattr(settings, "demo_mode_enabled", True)
    monkeypatch.setattr(settings, "demo_key", None)
    monkeypatch.setattr(settings, "clerk_jwks_url", None)

    r1 = await client.get("/interview/sessions", headers={"x-demo-session-id": "session-a"})
    r2 = await client.get("/interview/sessions", headers={"x-demo-session-id": "session-b"})
    assert r1.status_code == 200
    assert r2.status_code == 200

    from app.db.base import async_session_maker
    from app.models import User
    from sqlalchemy import select

    async with async_session_maker() as db:
        result = await db.execute(
            select(User).where(User.email.like("demo+%@sandbox.local"))
        )
        users = result.scalars().all()
    ids = {u.id for u in users}
    assert len(ids) >= 2
