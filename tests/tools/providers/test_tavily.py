"""Tests for the Tavily search provider."""

from __future__ import annotations

from types import SimpleNamespace

from src.tools.providers.tavily import TavilyProvider


def _fake_session(payload: dict, status_code: int = 200) -> SimpleNamespace:
    response = SimpleNamespace(
        status_code=status_code,
        json=lambda: payload,
        raise_for_status=lambda: None,
    )

    def fake_post(url, json=None, timeout=None):
        return response

    return SimpleNamespace(post=fake_post)


def test_missing_api_key_returns_empty(monkeypatch):
    """No ``TAVILY_API_KEY`` -> empty SearchResponse and unavailable provider."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    provider = TavilyProvider(api_key=None, session=_fake_session({}))

    assert provider.is_available() is False
    response = provider.search("q")

    assert response.provider == "tavily"
    assert response.results == []


def test_valid_response_parses_to_search_response(monkeypatch):
    """A mocked Tavily response is mapped into SearchResponse results."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    payload = {
        "results": [
            {
                "title": "NVIDIA supplies AI GPUs",
                "url": "https://example.com/nvidia-ai-gpu",
                "content": "NVIDIA is a major supplier of AI accelerators.",
                "published_date": "2026-06-20",
                "score": 0.91,
            },
            {
                "title": "AMD MI300 deployment",
                "url": "https://example.com/amd-mi300",
                "content": "AMD supplies AI accelerator products for data centers.",
                "published_date": "2026-06-21",
                "score": 0.83,
            },
        ]
    }
    provider = TavilyProvider(api_key="test-key", session=_fake_session(payload))

    response = provider.search("OpenAI ChatGPT GPU suppliers", max_results=2)

    assert provider.is_available() is True
    assert response.provider == "tavily"
    assert len(response.results) == 2
    assert response.results[0].title == "NVIDIA supplies AI GPUs"
    assert response.results[0].url == "https://example.com/nvidia-ai-gpu"
    assert response.results[0].snippet == "NVIDIA is a major supplier of AI accelerators."
    assert response.results[0].metadata["score"] == 0.91
    assert response.results[1].rank == 2


def test_session_error_returns_empty(monkeypatch):
    """If the Tavily session raises, the provider returns an empty response."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    def raising_session_post(url, json=None, timeout=None):
        raise RuntimeError("network down")

    provider = TavilyProvider(
        api_key="test-key",
        session=SimpleNamespace(post=raising_session_post),
    )

    response = provider.search("q")

    assert response.provider == "tavily"
    assert response.results == []
