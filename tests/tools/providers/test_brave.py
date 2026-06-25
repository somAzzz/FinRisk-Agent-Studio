"""Tests for the Brave search provider."""

from __future__ import annotations

from types import SimpleNamespace

from src.tools.providers.brave import BraveProvider


def _fake_session(payload: dict, status_code: int = 200) -> SimpleNamespace:
    response = SimpleNamespace(
        status_code=status_code,
        json=lambda: payload,
        raise_for_status=lambda: None,
    )

    def fake_get(url, headers=None, timeout=None):
        return response

    session = SimpleNamespace(get=fake_get)
    return session


def _capture_session(payload: dict) -> tuple[SimpleNamespace, dict]:
    captured: dict = {}
    response = SimpleNamespace(
        json=lambda: payload,
        raise_for_status=lambda: None,
    )

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return response

    return SimpleNamespace(get=fake_get), captured


def test_missing_api_key_returns_empty(monkeypatch):
    """No ``BRAVE_API_KEY`` -> empty SearchResponse (no exception)."""
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    provider = BraveProvider(api_key=None, session=_fake_session({}))

    assert provider.is_available() is False
    response = provider.search("q")

    assert response.provider == "brave"
    assert response.results == []


def test_valid_response_parses_to_search_response(monkeypatch):
    """A mocked Brave response is mapped into SearchResponse results."""
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    payload = {
        "web": {
            "results": [
                {
                    "title": "Result 1",
                    "url": "https://result1.com",
                    "description": "desc 1",
                },
                {
                    "title": "Result 2",
                    "url": "https://result2.com",
                    "description": "desc 2",
                },
            ]
        }
    }
    session = _fake_session(payload)
    provider = BraveProvider(api_key="test-key", session=session)

    assert provider.is_available() is True
    response = provider.search("q", max_results=2)

    assert response.provider == "brave"
    assert len(response.results) == 2
    assert response.results[0].title == "Result 1"
    assert response.results[0].url == "https://result1.com"
    assert response.results[1].rank == 2


def test_session_error_returns_empty(monkeypatch):
    """If the session raises, the provider returns an empty response."""
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    def raising_session_get(url, headers=None, timeout=None):
        raise RuntimeError("network down")

    session = SimpleNamespace(get=raising_session_get)
    provider = BraveProvider(api_key="test-key", session=session)

    response = provider.search("q")
    assert response.results == []


def test_brave_search_api_key_alias_is_supported(monkeypatch):
    """Official-style ``BRAVE_SEARCH_API_KEY`` configures the provider."""
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "alias-key")
    session, captured = _capture_session({"web": {"results": []}})

    provider = BraveProvider(api_key=None, session=session)

    assert provider.is_available() is True
    response = provider.search("q")

    assert response.provider == "brave"
    assert captured["headers"]["X-Subscription-Token"] == "alias-key"


def test_max_results_is_clamped_to_brave_count_range(monkeypatch):
    """Brave documents ``count`` as 1..20, so the provider clamps requests."""
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    session, captured = _capture_session({"web": {"results": []}})
    provider = BraveProvider(api_key="test-key", session=session)

    provider.search("q", max_results=50)

    assert "count=20" in captured["url"]
