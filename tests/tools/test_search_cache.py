"""Tests for the SQLite-backed SearchCache."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.tools.providers.base import SearchResponse, SearchResult
from src.tools.search_cache import SearchCache


def _sample_response(query: str = "q") -> SearchResponse:
    return SearchResponse(
        provider="fake",
        query=query,
        retrieved_at=datetime(2026, 6, 20, 12, 0, 0),
        results=[
            SearchResult(
                title="T",
                url=f"https://example.com/{query}",
                snippet="S",
                rank=1,
            )
        ],
        raw={"orig": True},
    )


def test_cache_round_trip_stores_and_retrieves(tmp_path):
    """A response written to the cache can be read back unchanged."""
    cache = SearchCache(cache_dir=tmp_path)
    response = _sample_response("rt")

    cache.set(response=response, ttl_seconds=60, query="rt")

    cached = cache.get(
        provider="fake",
        query="rt",
        params_hash=cache.make_key(
            provider="fake", query="rt", max_results=5, time_range=None, intent="general"
        ),
    )

    assert cached is not None
    assert cached.provider == "fake"
    assert cached.query == "rt"
    assert len(cached.results) == 1
    assert cached.results[0].url == "https://example.com/rt"


def test_cache_miss_returns_none(tmp_path):
    """An empty cache returns ``None`` on lookup."""
    cache = SearchCache(cache_dir=tmp_path)
    assert (
        cache.get(
            provider="fake",
            query="missing",
            params_hash=cache.make_key(
                provider="fake",
                query="missing",
                max_results=5,
                time_range=None,
                intent="general",
            ),
        )
        is None
    )


def test_cache_hit_does_not_call_provider(tmp_path):
    """Cached responses are returned without consulting the provider."""
    cache = SearchCache(cache_dir=tmp_path)
    provider_calls = {"count": 0}

    def fake_provider(query: str):
        provider_calls["count"] += 1
        return _sample_response(query)

    # Pre-populate the cache so the next call should hit.
    response = fake_provider("preloaded")
    cache.set(response=response, ttl_seconds=60, query="preloaded")

    # Simulate the router flow: cache.get() should return without provider call.
    cached = cache.get(
        provider="fake",
        query="preloaded",
        params_hash=cache.make_key(
            provider="fake",
            query="preloaded",
            max_results=5,
            time_range=None,
            intent="general",
        ),
    )
    assert cached is not None
    assert provider_calls["count"] == 1  # Only the priming call happened


def test_cache_ttl_expiration(tmp_path):
    """A response past its TTL is treated as a cache miss."""
    cache = SearchCache(cache_dir=tmp_path)
    response = _sample_response("expiring")

    cache.set(response=response, ttl_seconds=1, query="expiring")

    # Immediately after write it should still be cached.
    key = cache.make_key(
        provider="fake", query="expiring", max_results=5, time_range=None, intent="general"
    )
    assert cache.get(provider="fake", query="expiring", params_hash=key) is not None

    # Now manually rewrite the row's created_at so the TTL has elapsed.
    import sqlite3

    conn = sqlite3.connect(str(cache.db_path))
    try:
        conn.execute(
            "UPDATE search_cache SET created_at = ? WHERE key = ?",
            (int(datetime.now(timezone.utc).timestamp()) - 3600, key),
        )
        conn.commit()
    finally:
        conn.close()

    assert cache.get(provider="fake", query="expiring", params_hash=key) is None


def test_cache_key_includes_all_relevant_params():
    """The cache key is sensitive to provider, query, max_results, time_range, intent."""
    base = SearchCache.make_key(
        provider="p",
        query="q",
        max_results=5,
        time_range=None,
        intent="general",
    )
    assert base != SearchCache.make_key(
        provider="p2", query="q", max_results=5, time_range=None, intent="general"
    )
    assert base != SearchCache.make_key(
        provider="p", query="q2", max_results=5, time_range=None, intent="general"
    )
    assert base != SearchCache.make_key(
        provider="p", query="q", max_results=10, time_range=None, intent="general"
    )
    assert base != SearchCache.make_key(
        provider="p", query="q", max_results=5, time_range="w", intent="general"
    )
    assert base != SearchCache.make_key(
        provider="p", query="q", max_results=5, time_range=None, intent="news"
    )


def test_cache_clear(tmp_path):
    """``clear`` removes all rows from the cache."""
    cache = SearchCache(cache_dir=tmp_path)
    cache.set(response=_sample_response("a"), ttl_seconds=60, query="a")
    cache.set(response=_sample_response("b"), ttl_seconds=60, query="b")

    cache.clear()

    key_a = cache.make_key(
        provider="fake", query="a", max_results=5, time_range=None, intent="general"
    )
    key_b = cache.make_key(
        provider="fake", query="b", max_results=5, time_range=None, intent="general"
    )
    assert cache.get(provider="fake", query="a", params_hash=key_a) is None
    assert cache.get(provider="fake", query="b", params_hash=key_b) is None
