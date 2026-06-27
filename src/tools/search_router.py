"""SearchRouter — orchestrates multiple search providers with cache + fetch."""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from src.config import get_settings
from src.schemas.evidence import Evidence
from src.tools.providers.base import (
    SearchIntent,
    SearchProvider,
    SearchResponse,
    SearchResult,
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

LOW_QUALITY_SEARCH_DOMAINS: tuple[str, ...] = (
    "facebook.com",
    "instagram.com",
    "pinterest.",
    "tiktok.com",
    "threads.net",
    "linkedin.com/posts",
    "youtube.com/shorts",
)

PREFERRED_SEARCH_DOMAINS: tuple[str, ...] = (
    "sec.gov",
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "cnbc.com",
    "marketwatch.com",
    "federalregister.gov",
    "commerce.gov",
    "treasury.gov",
    "investor.",
    "/investor",
    "/ir/",
)

DEFAULT_TTL_SECONDS = 3600

WebFetcher = Callable[[str], Any]


# Intent-specific query templates. The user-supplied query is appended
# (when present) so callers always retain control of the core subject.
INTENT_QUERY_TEMPLATES: dict[str, str] = {
    "supply_chain": "{q} suppliers contract manufacturing outsourcing",
    "customer": "{q} customers order book demand concentration",
    "policy": "{q} regulation policy CHIPS IRA tariff export control",
    "geopolitical": "{q} geopolitical risk China Taiwan Middle East sanctions",
    "policy_risk": "{q} regulatory risk policy exposure",
    "geopolitical_risk": "{q} geopolitical exposure risk",
    "management_change": "{q} CEO CFO management change turnover",
    "product_demand": "{q} demand growth order book backlog product cycle",
    "litigation": "{q} litigation lawsuit SEC investigation antitrust",
    "product_supply_chain": "{q} product supply chain suppliers upstream components",
    "supplier_discovery": "{q} suppliers companies official partnership evidence",
    "component_supplier": "{q} major suppliers manufacturers market share",
    "cloud_dependency": "{q} cloud provider datacenter infrastructure supplier",
    "datacenter_power": "{q} datacenter power electricity supplier energy contract",
    "semiconductor_supply_chain": "{q} semiconductor upstream foundry HBM lithography suppliers",
}


def _apply_intent_template(intent: str, query: str) -> str | None:
    """Return the intent-augmented query, or ``None`` if no template.

    Returns ``None`` when the intent is ``"general"`` or unknown so the
    router can fall through to the bare user query.
    """
    template = INTENT_QUERY_TEMPLATES.get(intent)
    if template is None:
        return None
    return template.format(q=query)


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
    """Invoke ``fetcher(url)`` and resolve awaitables from sync code."""
    return fetcher(url)


def _run_awaitable_sync(awaitable: Any) -> Any:
    """Resolve an awaitable from sync code, even inside an active event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    outcome: dict[str, Any] = {}

    def runner() -> None:
        try:
            outcome["value"] = asyncio.run(awaitable)
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=runner, name="fintext-search-fetcher")
    thread.start()
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def _rank_search_response(
    response: SearchResponse,
    *,
    max_results: int,
) -> SearchResponse:
    scored: list[tuple[float, int, SearchResult]] = []
    for index, result in enumerate(response.results):
        score, reason, excluded = _source_quality(result)
        if excluded:
            continue
        metadata = {
            **result.metadata,
            "source_quality_score": score,
            "source_quality_reason": reason,
        }
        scored.append(
            (
                score,
                result.rank if result.rank is not None else index + 1,
                result.model_copy(update={"metadata": metadata}),
            )
        )

    scored.sort(key=lambda item: (-item[0], item[1]))
    ranked_results = [
        result.model_copy(update={"rank": rank})
        for rank, (_score, _old_rank, result) in enumerate(
            scored[:max_results],
            start=1,
        )
    ]
    return response.model_copy(update={"results": ranked_results})


def _source_quality(result: SearchResult) -> tuple[float, str, bool]:
    url = (result.url or "").strip()
    try:
        parsed = urlparse(url)
        haystack = f"{parsed.netloc}{parsed.path}".lower()
    except Exception:
        haystack = url.lower()

    if any(domain in haystack for domain in LOW_QUALITY_SEARCH_DOMAINS):
        return -100.0, "excluded_low_quality_domain", True

    score = 0.0
    reasons: list[str] = []
    if any(domain in haystack for domain in PREFERRED_SEARCH_DOMAINS):
        score += 3.0
        reasons.append("preferred_domain")
    if result.snippet.strip():
        score += 0.5
        reasons.append("has_snippet")
    else:
        score -= 0.5
        reasons.append("missing_snippet")
    if result.title.strip():
        score += 0.25
        reasons.append("has_title")
    return score, ",".join(reasons) or "neutral", False


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
        if providers is None:
            providers = self._build_default_providers()
        self.providers: list[SearchProvider] = list(providers)
        self.cache = cache or SearchCache(cache_dir=get_settings().cache_dir)
        self.blacklist: tuple[str, ...] = tuple(blacklist) if blacklist else DEFAULT_BLACKLIST
        self.default_ttl_seconds = default_ttl_seconds
        self._web_fetcher = web_fetcher

    @staticmethod
    def _build_default_providers() -> list[SearchProvider]:
        """Build the default provider list from ``SEARCH_PROVIDER_ORDER``.

        Order is read from :class:`Settings.search_provider_order` (a comma
        separated string such as ``"tavily,brave,duckduckgo"``). Providers with no
        API key configured are skipped so the router remains functional
        with zero keys.
        """
        from src.tools.providers.brave import BraveProvider
        from src.tools.providers.tavily import TavilyProvider

        order = get_settings().search_provider_order
        requested = [
            token.strip().lower() for token in order.split(",") if token.strip()
        ]
        factories: dict[str, Callable[[], SearchProvider]] = {
            "duckduckgo": DuckDuckGoProvider,
            "brave": BraveProvider,
            "tavily": TavilyProvider,
        }
        providers: list[SearchProvider] = []
        for name in requested:
            factory = factories.get(name)
            if factory is None:
                continue
            try:
                provider = factory()
            except Exception:
                continue
            if getattr(provider, "is_available", lambda: True)():
                providers.append(provider)
        if not providers:
            providers.append(DuckDuckGoProvider())
        return providers

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

        # Augment the user query with an intent-specific template so the
        # downstream LLM and report agent receive higher-signal results.
        templated_query = _apply_intent_template(intent, query)
        effective_query = templated_query or query

        for provider in self.providers:
            cached = self._cache_lookup(
                provider, effective_query, max_results, time_range, intent
            )
            if cached is not None:
                return _rank_search_response(cached, max_results=max_results)

        last_response: SearchResponse | None = None
        for provider in self.providers:
            if hasattr(provider, "is_available") and not provider.is_available():  # type: ignore[attr-defined]
                continue
            try:
                response = provider.search(
                    query=effective_query,
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
                ranked = _rank_search_response(response, max_results=max_results)
                if not ranked.results:
                    continue
                self._cache_store(ranked, ttl, max_results, time_range, intent)
                return ranked

        # All providers failed or returned empty; cache the last seen empty
        # response only when it's empty to avoid amplifying failures.
        if last_response is None:
            last_response = empty_response(
                _fallback_provider_name(self.providers), effective_query
            )
        if last_response.results:
            last_response = _rank_search_response(
                last_response,
                max_results=max_results,
            )
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
        with suppress(Exception):
            self.cache.set(
                response=response,
                ttl_seconds=ttl_seconds,
                max_results=max_results,
                time_range=time_range,
                intent=intent,
            )

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
                    fetch_result = _run_awaitable_sync(fetch_result)
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
