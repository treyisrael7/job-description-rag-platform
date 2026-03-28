"""
LLM-adjacent caches: retrieval chunks and evaluation payloads.

- Retrieval: keyed by document_id + question text hash (per product spec).
- Session JD pool: keyed by interview session_id (top-K chunks reused across questions in that session).
- Evaluation: keyed by document_id + question hash + answer hash (+ rubric fingerprint so JD rubric changes invalidate).

Uses Redis when REDIS_URL is set; otherwise a process-local TTL dict (thread-safe).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_REDIS: Any = None
_REDIS_DISABLED: bool = False
_MEMORY_LOCK = threading.Lock()
_MEMORY: dict[str, tuple[float, str]] = {}  # key -> (expires_at_unix, json_str)


def _normalize_for_hash(s: str) -> str:
    return " ".join((s or "").split())


def sha256_hex(s: str) -> str:
    return hashlib.sha256(_normalize_for_hash(s).encode("utf-8")).hexdigest()


def retrieval_cache_key(document_id: uuid.UUID, question: str) -> str:
    return f"interview:ret:v1:{document_id}:{sha256_hex(question)}"


def session_jd_pool_cache_key(session_id: uuid.UUID) -> str:
    """Top-K JD chunks for an interview session (reused across questions in that session)."""
    return f"interview:session:jd_pool:v1:{session_id}"


_SESSION_POOL_MEMORY: dict[str, tuple[float, str]] = {}
_SESSION_POOL_LOCK = threading.Lock()
# When CACHE_TTL_RETRIEVAL_SECONDS is 0, still keep a short process-local pool per session.
_SESSION_POOL_FALLBACK_TTL_SECONDS = 3600


def session_pool_get(session_id: uuid.UUID) -> Any | None:
    """Return cached JD chunk list for a session, or None."""
    from app.core.config import settings

    key = session_jd_pool_cache_key(session_id)
    ttl = settings.cache_ttl_retrieval_seconds
    if ttl > 0:
        raw = cache_get_json(key)
        return raw if isinstance(raw, list) else None
    now = time.time()
    with _SESSION_POOL_LOCK:
        ent = _SESSION_POOL_MEMORY.get(str(session_id))
        if ent is None:
            return None
        exp, js = ent
        if exp < now:
            del _SESSION_POOL_MEMORY[str(session_id)]
            return None
        try:
            val = json.loads(js)
        except json.JSONDecodeError:
            del _SESSION_POOL_MEMORY[str(session_id)]
            return None
        return val if isinstance(val, list) else None


def session_pool_set(session_id: uuid.UUID, chunks: list[Any]) -> None:
    """Store JD chunk list for a session (Redis/memory or short process-local fallback)."""
    from app.core.config import settings

    key = session_jd_pool_cache_key(session_id)
    ttl = settings.cache_ttl_retrieval_seconds
    payload = json.dumps(chunks, ensure_ascii=False, default=str)
    if ttl > 0:
        cache_set_json(key, chunks, ttl)
        return
    exp = time.time() + _SESSION_POOL_FALLBACK_TTL_SECONDS
    with _SESSION_POOL_LOCK:
        _SESSION_POOL_MEMORY[str(session_id)] = (exp, payload)
        if len(_SESSION_POOL_MEMORY) > 2000:
            _evict_session_pool_memory_unlocked(time.time())


def _evict_session_pool_memory_unlocked(now: float) -> None:
    dead = [k for k, (exp, _) in _SESSION_POOL_MEMORY.items() if exp < now]
    for k in dead[:1000]:
        _SESSION_POOL_MEMORY.pop(k, None)


def evaluation_cache_key(
    document_id: uuid.UUID,
    question: str,
    answer: str,
    document_rubric_json: list[dict] | None,
    evaluation_mode: str = "full",
) -> str:
    rubric_raw = json.dumps(document_rubric_json or [], sort_keys=True, ensure_ascii=False)
    rubric_fp = hashlib.sha256(rubric_raw.encode("utf-8")).hexdigest()[:24]
    mode = (evaluation_mode or "full").strip().lower() or "full"
    return (
        f"interview:eval:v1:{document_id}:{sha256_hex(question)}:"
        f"{sha256_hex(answer)}:{rubric_fp}:{mode}"
    )


def _redis_client():
    global _REDIS, _REDIS_DISABLED
    if _REDIS_DISABLED:
        return None
    if _REDIS is not None:
        return _REDIS
    from app.core.config import settings

    if not settings.redis_url:
        return None
    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        client.ping()
        _REDIS = client
        logger.info("LLM cache: using Redis")
        return _REDIS
    except Exception as e:
        logger.warning("LLM cache: Redis unavailable (%s); using in-memory cache", e)
        _REDIS_DISABLED = True
        return None


def cache_get_json(key: str) -> Any | None:
    """Return deserialized JSON or None on miss / error."""
    r = _redis_client()
    try:
        if r is not None:
            raw = r.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        now = time.time()
        with _MEMORY_LOCK:
            entry = _MEMORY.get(key)
            if entry is None:
                return None
            exp, js = entry
            if exp < now:
                del _MEMORY[key]
                return None
            return json.loads(js)
    except Exception as e:
        logger.debug("cache get failed key=%s: %s", key, e)
        return None


def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return
    payload = json.dumps(value, ensure_ascii=False, default=str)
    r = _redis_client()
    try:
        if r is not None:
            r.setex(key, ttl_seconds, payload)
            return
        exp = time.time() + ttl_seconds
        with _MEMORY_LOCK:
            _MEMORY[key] = (exp, payload)
            # crude cap to avoid unbounded growth
            if len(_MEMORY) > 10_000:
                _evict_expired_memory_unlocked(now=time.time())
    except Exception as e:
        logger.debug("cache set failed key=%s: %s", key, e)


def _evict_expired_memory_unlocked(now: float) -> None:
    dead = [k for k, (exp, _) in _MEMORY.items() if exp < now]
    for k in dead[:5000]:
        _MEMORY.pop(k, None)
