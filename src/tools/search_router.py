"""SearchRouter — orchestrates multiple search providers with cache + fetch."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from src.config import get_settings
from src.schemas.evidence import Evidence
from src.tools.providers.base import (
    SearchIntent,
    SearchProvider,
    SearchResponse,
    TimeRange,
    empty_response,
)
from src.tools.providers.duckduckgo import DuckDuckGoProvider
from src.tools.search_cache import SearchCache

DEFAULT_BLACKLIST: tuple[str, ...] = (
    "consent.yahoo.com",
    "google.com/sorry",
    "investor.apple.com",
)

DEFAULT_TTL_SECONDS = 3600

WebFetcher = Callable[[str], Any]


@dataclass
class WebFetchResultSummary:
    """A trimmed version of :class:`WebFetchResult` for router consumers."""

    url: str
    content: str
    status_code: int
    error: str | None = None


class EvidenceConversionError(ValueError):
    """Raised when a SearchResult cannot be converted to Evidence."""


def to_evidence(
    response: SearchResponse,
    result_index: int = 0,
    confidence: float = 0.7,
) -> Evidence:
    """Convert a single ``SearchResponse`` result into an :class:`Evidence`.

    The conversion is intentionally lightweight: the snippet is used as the
    ``quote``, and metadata captures the provider, rank, and query. If the
    response contains no results, a ``EvidenceConversionError`` is raised.
    """
    if not response.results:
        raise EvidenceConversionError(
            f"SearchResponse has no results (provider={response.provider!r})"
        )

    if result_index < 0 or result_index >= len(response.results):
        raise EvidenceConversionError(
            f"result_index {result_index} out of range "
            f"(0..{len(response.results) - 1})"
        )

    result = response.results[result_index]
    quote = (result.snippet or result.title or "").strip()
    if not quote:
        raise EvidenceConversionError("Result has neither snippet nor title")

    metadata: dict[str, Any] = {
        "provider": response.provider,
        "rank": result.rank,
        "query": response.query,
        **result.metadata,
    }

    return Evidence(
        evidence_id=f"web:{result.url}",
        source_type="web",
        source_id=response.provider,
        title=result.title or None,
        url=result.url,
        quote=quote,
        retrieved_at=response.retrieved_at,
        published_at=result.published_at,
        confidence=confidence,
        metadata=metadata,
    )


def _call_fetcher(fetcher: WebFetcher, url: str) -> Any:
    """Invoke ``fetcher(url)`` and return its result unchanged.

    Async fetchers are *not* awaited here; the router's ``fetch_search_results``
    runs them via :func:`asyncio.run` because the router operates in
    synchronous agent loops.
    """
    return fetcher(url)


class SearchRouter:
    """Route search requests across providers, with cache and fetch support."""

    def __init__(
        self,
        providers: Sequence[SearchProvider] | None = None,
        cache: SearchCache | None = None,
        blacklist: Sequence[str] | None = None,
        default_ttl_seconds: int = DEFAULT_TTL_SECONDS,
        web_fetcher: WebFetcher | None = None,
    ):
        self.providers: list[SearchProvider] = (
            list(providers) if providers is not None else [DuckDuckGoProvider()]
        )
        self.cache = cache or SearchCache(cache_dir=get_settings().cache_dir)
        self.blacklist: tuple[str, ...] = tuple(blacklist) if blacklist else DEFAULT_BLACKLIST
        self.default_ttl_seconds = default_ttl_seconds
        self._web_fetcher = web_fetcher

    def search(
        self,
        query: str,
        intent: SearchIntent = "general",
        max_results: int = 5,
        time_range: TimeRange = None,
        ttl_seconds: int | None = None,
    ) -> SearchResponse:
        """Search via the configured providers, falling back on failure.

        Order of operations:
        1. Check the cache; return on hit.
        2. Iterate providers, skipping those reporting ``is_available() == False``.
        3. Return the first non-empty response.
        4. Cache the chosen response and return it.
        5. If all providers fail, return an empty ``SearchResponse``.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds

        for provider in self.providers:
            cached = self._cache_lookup(provider, query, max_results, time_range, intent)
            if cached is not None:
                return cached

        last_response: SearchResponse | None = None
        for provider in self.providers:
            if hasattr(provider, "is_available") and not provider.is_available():  # type: ignore[attr-defined]
                continue
            try:
                response = provider.search(
                    query=query,
                    max_results=max_results,
                    time_range=time_range,
                )
            except Exception:
                # Defensive: provider contract says it shouldn't raise, but
                # we still guard against it so the router never crashes.
                continue

            if response is None:
                continue

            last_response = response
            if response.results:
                self._cache_store(response, ttl, max_results, time_range, intent)
                return response

        # All providers failed or returned empty; cache the last seen empty
        # response only when it's empty to avoid amplifying failures.
        if last_response is None:
            last_response = empty_response(_fallback_provider_name(self.providers), query)

        if last_response.results:
            self._cache_store(last_response, ttl, max_results, time_range, intent)
        return last_response

    def _cache_lookup(
        self,
        provider: SearchProvider,
        query: str,
        max_results: int,
        time_range: TimeRange,
        intent: SearchIntent,
    ) -> SearchResponse | None:
        provider_name = getattr(provider, "provider_name", "") or provider.__class__.__name__
        return self.cache.get(
            provider=provider_name,
            query=query,
            params_hash=self.cache.make_key(
                provider=provider_name,
                query=query,
                max_results=max_results,
                time_range=time_range,
                intent=intent,
            ),
            max_results=max_results,
            time_range=time_range,
            intent=intent,
        )

    def _cache_store(
        self,
        response: SearchResponse,
        ttl_seconds: int,
        max_results: int,
        time_range: TimeRange,
        intent: SearchIntent,
    ) -> None:
        try:
            self.cache.set(
                response=response,
                ttl_seconds=ttl_seconds,
                max_results=max_results,
                time_range=time_range,
                intent=intent,
            )
        except Exception:
            # Cache write errors must not break the search path.
            pass

    def fetch_search_results(
        self,
        response: SearchResponse,
        max_pages: int = 3,
        fetcher: WebFetcher | None = None,
    ) -> list[WebFetchResultSummary]:
        """Fetch each unique, non-blacklisted result URL.

        Returns a list of :class:`WebFetchResultSummary` instances. Errors are
        captured per-URL rather than raising, so a single failure does not
        abort the entire batch.

        A custom ``fetcher`` callable can be supplied for tests; when omitted,
        the router uses :func:`src.tools.web_fetch.web_fetch_sync` so this
        method remains usable from synchronous code (LLM agent loop).
        """
        if not response or not response.results:
            return []

        seen: set[str] = set()
        urls: list[str] = []
        for result in response.results:
            url = (result.url or "").strip()
            if not url or url in seen:
                continue
            if self._is_blacklisted(url):
                continue
            seen.add(url)
            urls.append(url)
            if len(urls) >= max_pages:
                break

        if not urls:
            return []

        fetcher_callable: WebFetcher = fetcher or self._resolve_default_fetcher()

        summaries: list[WebFetchResultSummary] = []
        for url in urls:
            try:
                fetch_result = _call_fetcher(fetcher_callable, url)
                if inspect.isawaitable(fetch_result):
                    # Async fetchers must be awaited by the caller; surface
                    # this as an error rather than blocking here.
                    fetch_result = asyncio.run(fetch_result)
            except Exception as exc:
                summaries.append(
                    WebFetchResultSummary(
                        url=url,
                        content="",
                        status_code=0,
                        error=f"FETCH_ERROR: {exc!s}",
                    )
                )
                continue

            summaries.append(self.result_summary_from_fetch(fetch_result))
        return summaries

    def _resolve_default_fetcher(self) -> WebFetcher:
        """Return the default web fetcher, preferring ``web_fetch_sync``."""
        if self._web_fetcher is not None:
            return self._web_fetcher
        # Use the synchronous wrapper so this method works from non-async code.
        from src.tools.web_fetch import web_fetch_sync

        return web_fetch_sync

    def _is_blacklisted(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            haystack = (parsed.netloc + parsed.path).lower()
        except Exception:
            return False
        for entry in self.blacklist:
            entry_l = entry.lower()
            if entry_l in haystack:
                return True
        return False

    @staticmethod
    def result_summary_from_fetch(fetch_result: Any) -> WebFetchResultSummary:
        """Convert a ``WebFetchResult`` into the router's lightweight summary."""
        if getattr(fetch_result, "status", "success") == "failed":
            error_code = getattr(fetch_result, "error_code", None) or "UNKNOWN"
            error_message = getattr(fetch_result, "error_message", None) or "fetch failed"
            return WebFetchResultSummary(
                url=getattr(fetch_result, "url", ""),
                content="",
                status_code=0,
                error=f"{error_code}: {error_message}",
            )

        content = getattr(fetch_result, "content", "") or ""
        status_code = 200 if getattr(fetch_result, "status", "success") == "success" else 500
        return WebFetchResultSummary(
            url=getattr(fetch_result, "url", ""),
            content=content,
            status_code=status_code,
            error=None,
        )


def _fallback_provider_name(providers: Sequence[SearchProvider]) -> str:
    for provider in providers:
        name = getattr(provider, "provider_name", "") or ""
        if name:
            return name
    return "unknown"


__all__ = [
    "DEFAULT_BLACKLIST",
    "DEFAULT_TTL_SECONDS",
    "EvidenceConversionError",
    "SearchRouter",
    "WebFetchResultSummary",
    "to_evidence",
]
