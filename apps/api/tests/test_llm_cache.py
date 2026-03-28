"""LLM retrieval / evaluation cache keys and in-memory backend."""

import uuid

from app.core.llm_cache import (
    cache_get_json,
    cache_set_json,
    evaluation_cache_key,
    retrieval_cache_key,
    session_jd_pool_cache_key,
    sha256_hex,
)


def test_sha256_hex_normalizes_whitespace() -> None:
    assert sha256_hex("a  b") == sha256_hex("a b")


def test_retrieval_cache_key_stable() -> None:
    d = uuid.uuid4()
    assert retrieval_cache_key(d, "What is your experience?") == retrieval_cache_key(
        d, "What is your experience?"
    )


def test_evaluation_cache_key_includes_rubric() -> None:
    d = uuid.uuid4()
    k1 = evaluation_cache_key(d, "Q", "A", None)
    k2 = evaluation_cache_key(d, "Q", "A", [{"name": "X", "description": "y"}])
    assert k1 != k2


def test_evaluation_cache_key_includes_mode() -> None:
    d = uuid.uuid4()
    k_lite = evaluation_cache_key(d, "Q", "A", None, "lite")
    k_full = evaluation_cache_key(d, "Q", "A", None, "full")
    assert k_lite != k_full


def test_session_jd_pool_cache_key_stable() -> None:
    s = uuid.uuid4()
    assert session_jd_pool_cache_key(s) == session_jd_pool_cache_key(s)
    assert session_jd_pool_cache_key(s) != session_jd_pool_cache_key(uuid.uuid4())


def test_memory_cache_roundtrip() -> None:
    key = f"test:llm_cache:{uuid.uuid4().hex}"
    cache_set_json(key, {"score": 7.5, "nested": {"a": [1, 2]}}, 120)
    assert cache_get_json(key) == {"score": 7.5, "nested": {"a": [1, 2]}}
