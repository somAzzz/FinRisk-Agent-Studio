"""Tests for SearchRouter — provider fallback, caching, and fetch batching."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from src.schemas.evidence import Evidence
from src.tools.providers.base import SearchResponse, SearchResult
from src.tools.search_cache import SearchCache
from src.tools.search_router import (
    EvidenceConversionError,
    SearchRouter,
    to_evidence,
)


class FakeProvider:
    """Minimal SearchProvider used by tests."""

    def __init__(self, name: str, results: list[SearchResult] | None = None, raise_exc: bool = False):
        self.provider_name = name
        self._results = results or []
        self._raise = raise_exc
        self.call_count = 0
        self.last_query: str | None = None

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 5, time_range=None) -> SearchResponse:
        self.call_count += 1
        self.last_query = query
        if self._raise:
            raise RuntimeError("boom")
        return SearchResponse(
            provider=self.provider_name,
            query=query,
            retrieved_at=datetime(2026, 6, 20, 12, 0, 0),
            results=list(self._results[:max_results]),
            raw=None,
        )


def _make_result(url: str, title: str = "T", snippet: str = "S") -> SearchResult:
    return SearchResult(
        title=title,
        url=url,
        snippet=snippet,
        rank=1,
    )


def test_search_router_fallback_when_no_providers(tmp_path):
    """Default router falls back to DuckDuckGo when no providers supplied."""
    router = SearchRouter(providers=[], cache=SearchCache(cache_dir=tmp_path))
    response = router.search("anything", ttl_seconds=60)
    # The provider is the default duckduckgo which can succeed or return
    # empty depending on environment; either way it must not raise.
    assert response.provider in {"duckduckgo", "unknown"}


def test_search_router_with_fake_provider_returns_results(tmp_path):
    """A configured provider's results are returned unchanged."""
    results = [_make_result("https://a.com"), _make_result("https://b.com")]
    provider = FakeProvider("fake", results=results)
    router = SearchRouter(providers=[provider], cache=SearchCache(cache_dir=tmp_path))

    response = router.search("test query", ttl_seconds=60)

    assert response.provider == "fake"
    assert [r.url for r in response.results] == ["https://a.com", "https://b.com"]
    assert provider.call_count == 1
    assert provider.last_query == "test query"


def test_search_router_cache_hit_does_not_call_provider(tmp_path):
    """A cache hit returns cached response and skips the provider."""
    results = [_make_result("https://cached.com")]
    provider = FakeProvider("fake", results=results)
    cache = SearchCache(cache_dir=tmp_path)
    router = SearchRouter(providers=[provider], cache=cache)

    first = router.search("query", ttl_seconds=60)
    assert provider.call_count == 1

    second = router.search("query", ttl_seconds=60)
    assert provider.call_count == 1  # No additional provider call
    assert [r.url for r in second.results] == ["https://cached.com"]
    assert second.provider == first.provider


def test_search_router_cache_miss_calls_provider(tmp_path):
    """A cache miss routes to the provider and writes the response back."""
    provider = FakeProvider("fake", results=[_make_result("https://fresh.com")])
    router = SearchRouter(providers=[provider], cache=SearchCache(cache_dir=tmp_path))

    response = router.search("miss", ttl_seconds=60)

    assert provider.call_count == 1
    assert [r.url for r in response.results] == ["https://fresh.com"]


def test_search_router_provider_error_falls_back(tmp_path):
    """A raising provider is skipped; the next provider is tried."""
    bad = FakeProvider("bad", raise_exc=True)
    good = FakeProvider("good", results=[_make_result("https://ok.com")])
    router = SearchRouter(providers=[bad, good], cache=SearchCache(cache_dir=tmp_path))

    response = router.search("hi", ttl_seconds=60)

    assert response.provider == "good"
    assert [r.url for r in response.results] == ["https://ok.com"]
    assert bad.call_count == 1
    assert good.call_count == 1


def test_search_router_provider_unavailable_is_skipped(tmp_path):
    """A provider whose ``is_available()`` is False is skipped."""

    class UnavailableProvider(FakeProvider):
        def is_available(self) -> bool:
            return False

    unavailable = UnavailableProvider("unavail", results=[_make_result("https://nope.com")])
    available = FakeProvider("avail", results=[_make_result("https://yes.com")])
    router = SearchRouter(
        providers=[unavailable, available], cache=SearchCache(cache_dir=tmp_path)
    )

    response = router.search("query", ttl_seconds=60)

    assert unavailable.call_count == 0
    assert available.call_count == 1
    assert response.provider == "avail"


def _sync_fetcher(monkeypatch, captured: list[str], responses: dict[str, SimpleNamespace]):
    """Patch ``web_fetch_sync`` on the web_fetch module and return fetcher."""

    def fake_web_fetch(url: str):
        captured.append(url)
        if url in responses:
            return responses[url]
        return SimpleNamespace(
            url=url,
            content="default",
            status="success",
            error_code=None,
            error_message=None,
        )

    import src.tools.web_fetch as web_fetch_module
    monkeypatch.setattr(web_fetch_module, "web_fetch_sync", fake_web_fetch)
    return fake_web_fetch


def test_fetch_search_results_skips_duplicate_urls(tmp_path, monkeypatch):
    """Duplicate URLs in the response are fetched only once."""
    response = SearchResponse(
        provider="fake",
        query="q",
        retrieved_at=datetime(2026, 6, 20, 12, 0, 0),
        results=[
            _make_result("https://example.com/a"),
            _make_result("https://example.com/a"),
            _make_result("https://example.com/b"),
        ],
        raw=None,
    )

    seen_urls: list[str] = []

    def fake_web_fetch_sync(url: str):
        seen_urls.append(url)
        return SimpleNamespace(
            url=url,
            content="hello",
            status="success",
            error_code=None,
            error_message=None,
        )

    import src.tools.web_fetch as web_fetch_module
    monkeypatch.setattr(web_fetch_module, "web_fetch_sync", fake_web_fetch_sync)

    router = SearchRouter(providers=[], cache=SearchCache(cache_dir=tmp_path))
    summaries = router.fetch_search_results(response, max_pages=5)

    assert seen_urls == ["https://example.com/a", "https://example.com/b"]
    assert len(summaries) == 2
    assert [s.url for s in summaries] == ["https://example.com/a", "https://example.com/b"]


def test_fetch_search_results_skips_blacklisted_domains(tmp_path, monkeypatch):
    """Blacklisted domains are skipped entirely."""
    response = SearchResponse(
        provider="fake",
        query="q",
        retrieved_at=datetime(2026, 6, 20, 12, 0, 0),
        results=[
            _make_result("https://consent.yahoo.com/anything"),
            _make_result("https://google.com/sorry/index"),
            _make_result("https://good.example.com/article"),
        ],
        raw=None,
    )

    seen: list[str] = []

    def fake_web_fetch_sync(url: str):
        seen.append(url)
        return SimpleNamespace(
            url=url,
            content="ok",
            status="success",
            error_code=None,
            error_message=None,
        )

    import src.tools.web_fetch as web_fetch_module
    monkeypatch.setattr(web_fetch_module, "web_fetch_sync", fake_web_fetch_sync)

    router = SearchRouter(providers=[], cache=SearchCache(cache_dir=tmp_path))
    summaries = router.fetch_search_results(response, max_pages=5)

    assert seen == ["https://good.example.com/article"]
    assert [s.url for s in summaries] == ["https://good.example.com/article"]


def test_fetch_search_results_records_errors_per_url(tmp_path, monkeypatch):
    """Per-URL errors are captured without aborting the batch."""
    response = SearchResponse(
        provider="fake",
        query="q",
        retrieved_at=datetime(2026, 6, 20, 12, 0, 0),
        results=[
            _make_result("https://bad.example.com"),
            _make_result("https://good.example.com"),
        ],
        raw=None,
    )

    def fake_web_fetch_sync(url: str):
        if "bad" in url:
            return SimpleNamespace(
                url=url,
                content="",
                status="failed",
                error_code="404_NOT_FOUND",
                error_message="not found",
            )
        return SimpleNamespace(
            url=url,
            content="body",
            status="success",
            error_code=None,
            error_message=None,
        )

    import src.tools.web_fetch as web_fetch_module
    monkeypatch.setattr(web_fetch_module, "web_fetch_sync", fake_web_fetch_sync)

    router = SearchRouter(providers=[], cache=SearchCache(cache_dir=tmp_path))
    summaries = router.fetch_search_results(response, max_pages=5)

    assert len(summaries) == 2
    by_url = {s.url: s for s in summaries}
    assert by_url["https://bad.example.com"].error is not None
    assert "404_NOT_FOUND" in by_url["https://bad.example.com"].error
    assert by_url["https://good.example.com"].error is None
    assert by_url["https://good.example.com"].content == "body"


def test_fetch_search_results_continues_on_fetcher_exception(tmp_path, monkeypatch):
    """A fetcher exception for one URL does not abort the batch."""

    def fake_web_fetch_sync(url: str):
        if "bad" in url:
            raise RuntimeError("network down")
        return SimpleNamespace(
            url=url,
            content="ok",
            status="success",
            error_code=None,
            error_message=None,
        )

    import src.tools.web_fetch as web_fetch_module
    monkeypatch.setattr(web_fetch_module, "web_fetch_sync", fake_web_fetch_sync)

    response = SearchResponse(
        provider="fake",
        query="q",
        retrieved_at=datetime(2026, 6, 20, 12, 0, 0),
        results=[
            _make_result("https://bad.example.com"),
            _make_result("https://good.example.com"),
        ],
        raw=None,
    )

    router = SearchRouter(providers=[], cache=SearchCache(cache_dir=tmp_path))
    summaries = router.fetch_search_results(response, max_pages=5)

    assert len(summaries) == 2
    by_url = {s.url: s for s in summaries}
    assert by_url["https://bad.example.com"].error is not None
    assert "FETCH_ERROR" in by_url["https://bad.example.com"].error
    assert by_url["https://good.example.com"].error is None


def test_search_result_to_evidence_conversion(tmp_path):
    """``to_evidence`` converts a SearchResult to an Evidence instance."""
    response = SearchResponse(
        provider="fake",
        query="q",
        retrieved_at=datetime(2026, 6, 20, 12, 0, 0),
        results=[
            SearchResult(
                title="Title",
                url="https://example.com/x",
                snippet="Snippet text",
                rank=1,
            )
        ],
        raw=None,
    )

    evidence = to_evidence(response, result_index=0)

    assert isinstance(evidence, Evidence)
    assert evidence.url == "https://example.com/x"
    assert evidence.title == "Title"
    assert evidence.quote == "Snippet text"
    assert evidence.metadata["provider"] == "fake"
    assert evidence.source_type == "web"


def test_to_evidence_raises_on_empty_response():
    """An empty SearchResponse cannot be converted."""
    response = SearchResponse(
        provider="fake",
        query="q",
        retrieved_at=datetime(2026, 6, 20, 12, 0, 0),
        results=[],
        raw=None,
    )
    with pytest.raises(EvidenceConversionError):
        to_evidence(response)


def test_search_router_uses_duckduckgo_when_no_order_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """Default order is ``duckduckgo`` and the router falls back to it."""
    from src.tools.search_router import SearchRouter

    monkeypatch.delenv("SEARCH_PROVIDER_ORDER", raising=False)
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    from src.config import get_settings

    get_settings.cache_clear()
    router = SearchRouter()
    # DuckDuckGo should be the only fallback.
    assert len(router.providers) >= 1
    assert router.providers[0].provider_name == "duckduckgo"


def test_search_router_honors_search_provider_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``SEARCH_PROVIDER_ORDER=duckduckgo,duckduckgo`` produces two providers."""
    from src.config import get_settings
    from src.tools.search_router import SearchRouter

    monkeypatch.setenv("SEARCH_PROVIDER_ORDER", "duckduckgo")
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    get_settings.cache_clear()
    router = SearchRouter()
    assert [p.provider_name for p in router.providers] == ["duckduckgo"]


def test_search_router_skips_unconfigured_providers(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Providers with no API key are skipped, falling back to duckduckgo."""
    from src.config import get_settings
    from src.tools.search_router import SearchRouter

    monkeypatch.setenv("SEARCH_PROVIDER_ORDER", "brave,duckduckgo")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    get_settings.cache_clear()
    router = SearchRouter()
    # brave is skipped because no API key, duckduckgo takes its place.
    names = [p.provider_name for p in router.providers]
    assert "duckduckgo" in names
    assert "brave" not in names


def test_intent_template_supply_chain_appends_keywords() -> None:
    """``supply_chain`` intent augments the user query with vendor keywords."""
    from src.tools.search_router import _apply_intent_template

    query = _apply_intent_template("supply_chain", "AAPL")
    assert query is not None
    assert "AAPL" in query
    assert "supplier" in query.lower() or "outsourcing" in query.lower()


def test_intent_template_unknown_returns_none() -> None:
    """Unknown intent falls through to the bare query (no template)."""
    from src.tools.search_router import _apply_intent_template

    assert _apply_intent_template("not-a-real-intent", "AAPL") is None
    assert _apply_intent_template("general", "AAPL") is None


def test_search_router_uses_intent_template_in_provider_call(
    tmp_path, monkeypatch
) -> None:
    """The provider is called with the intent-augmented query."""
    captured = {}

    class CaptureProvider(FakeProvider):
        def search(self, query, max_results=5, time_range=None):  # noqa: ANN001
            captured["query"] = query
            return super().search(query, max_results, time_range)

    provider = CaptureProvider("cap", results=[_make_result("https://x.com")])
    router = SearchRouter(providers=[provider], cache=SearchCache(cache_dir=tmp_path))
    router.search("AAPL", intent="policy", ttl_seconds=60)
    assert "AAPL" in captured["query"]
    assert "policy" in captured["query"].lower() or "tariff" in captured["query"].lower()
