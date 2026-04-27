"""Clerk JWT verification and authenticated user helpers."""

import logging
import uuid
from typing import Any
from urllib.parse import urlparse

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models import User

logger = logging.getLogger(__name__)

_jwks_client: PyJWKClient | None = None

_DEMO_USER_EMAIL = "demo@sandbox.local"
_DEMO_SESSION_NAMESPACE = uuid.UUID("7a6eb1d9-43af-4972-b843-4c33ccf61e82")


def extract_bearer_token(request: Request) -> str | None:
    """Return the Bearer token string if present and non-empty; else None."""
    auth = request.headers.get("authorization")
    if not auth:
        return None
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer":
        return None
    t = token.strip()
    return t if t else None


def _demo_and_bearer_conflict(request: Request) -> bool:
    return bool(
        settings.demo_key
        and extract_bearer_token(request)
        and request.headers.get("x-demo-key") is not None
    )


def _demo_session_id_from_request(request: Request) -> str | None:
    """Return a bounded, non-secret browser demo session id."""
    raw = (request.headers.get("x-demo-session-id") or "").strip()
    if not raw:
        return None
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in ("-", "_"))
    return safe[:128] or None


def _issuer_from_jwks_url(url: str) -> str:
    """Derive issuer from JWKS URL: https://x.clerk.accounts.dev/.well-known/jwks.json -> https://x.clerk.accounts.dev"""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = settings.clerk_jwks_url
        if not url:
            raise ValueError("CLERK_JWKS_URL is not configured")
        _jwks_client = PyJWKClient(url, cache_jwk_set=True)
    return _jwks_client


def verify_clerk_token(token: str) -> str | None:
    """
    Verify Clerk JWT and return the subject (Clerk user ID).
    Returns None on invalid/expired token.
    """
    if not settings.clerk_jwks_url:
        return None
    try:
        jwks = _get_jwks_client()
        signing_key = jwks.get_signing_key_from_jwt(token)
    except Exception as e:
        logger.warning("Clerk token signing key lookup failed: %s", e)
        return None
    issuer = settings.clerk_issuer or _issuer_from_jwks_url(settings.clerk_jwks_url)
    # Try with issuer first; fallback without issuer for some Clerk setups
    for verify_iss in (True, False):
        try:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=issuer if verify_iss else None,
                leeway=120,  # Allow 2min clock skew (iat/nbf/exp) — Docker on Windows often lags
                options={
                    "verify_exp": True,
                    "verify_aud": False,
                    "verify_iss": verify_iss,
                },
            )
            return payload.get("sub")
        except jwt.InvalidIssuerError as e:
            if verify_iss:
                logger.info("Clerk issuer mismatch, retrying without issuer check: %s", e)
                continue
            raise
        except Exception as e:
            logger.warning("Clerk token verification failed: %s", e)
            return None
    return None


async def get_or_create_user_by_clerk_id(db: AsyncSession, clerk_id: str) -> User:
    """Get an existing user by Clerk ID, or create one."""
    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(id=uuid.uuid4(), clerk_id=clerk_id, email=f"{clerk_id}@clerk.user")
    db.add(user)
    await db.flush()
    return user


async def get_or_create_demo_user(db: AsyncSession, session_id: str | None = None) -> User:
    """Sandbox user for demo mode only; isolated by anonymous browser session."""
    if session_id:
        uid = uuid.uuid5(_DEMO_SESSION_NAMESPACE, session_id)
        email = f"demo+{uid.hex[:12]}@sandbox.local"
    else:
        uid = settings.demo_user_id
        email = _DEMO_USER_EMAIL
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(id=uid, clerk_id=None, email=email)
    db.add(user)
    await db.flush()
    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Bearer (non-empty) → verify Clerk JWT and resolve the real user when Clerk is configured.
    Otherwise, when demo mode is enabled, resolve the fixed sandbox user.
    """
    if _demo_and_bearer_conflict(request):
        raise HTTPException(
            status_code=400,
            detail="Do not send x-demo-key together with a Bearer token; use one authentication method.",
        )

    bearer = extract_bearer_token(request)
    if bearer and settings.clerk_jwks_url:
        clerk_id = verify_clerk_token(bearer)
        if clerk_id:
            user = await get_or_create_user_by_clerk_id(db, clerk_id)
            await db.commit()
            await db.refresh(user)
            return user
        if not settings.demo_auth_active:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired session. Please sign in again.",
            )

    if settings.demo_auth_active:
        user = await get_or_create_demo_user(
            db,
            session_id=_demo_session_id_from_request(request),
        )
        await db.commit()
        await db.refresh(user)
        return user

    raise HTTPException(status_code=401, detail="Authentication required")


def assert_resource_ownership(resource: Any, current_user: User) -> None:
    """Raise when a resource is missing or belongs to another user."""
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    owner_id = getattr(resource, "user_id", None)
    if owner_id is None:
        raise ValueError("Resource does not expose user_id for ownership checks")

    if owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
