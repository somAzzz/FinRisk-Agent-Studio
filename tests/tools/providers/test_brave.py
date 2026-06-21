"""Tests for the Brave search provider."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

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


def test_missing_api_key_returns_empty(monkeypatch):
    """No ``BRAVE_API_KEY`` -> empty SearchResponse (no exception)."""
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    provider = BraveProvider(api_key=None, session=_fake_session({}))

    response = provider.search("q")

    assert response.provider == "brave"
    assert response.results == []


def test_valid_response_parses_to_search_response(monkeypatch):
    """A mocked Brave response is mapped into SearchResponse results."""
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
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

    response = provider.search("q", max_results=2)

    assert response.provider == "brave"
    assert len(response.results) == 2
    assert response.results[0].title == "Result 1"
    assert response.results[0].url == "https://result1.com"
    assert response.results[1].rank == 2


def test_session_error_returns_empty(monkeypatch):
    """If the session raises, the provider returns an empty response."""
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)

    def raising_session_get(url, headers=None, timeout=None):
        raise RuntimeError("network down")

    session = SimpleNamespace(get=raising_session_get)
    provider = BraveProvider(api_key="test-key", session=session)

    response = provider.search("q")
    assert response.results == []
