"""Tests for the DuckDuckGo provider."""

from __future__ import annotations

import json

import pytest

from src.tools.providers.duckduckgo import DuckDuckGoProvider


def _envelope(results: list[dict] | None = None, error: str | None = None) -> str:
    if error is not None:
        return json.dumps({"error": error})
    payload = {
        "retrieved_at": "2026-06-20T12:00:00Z",
        "query_used": "q",
        "time_range_applied": None,
        "results": results or [],
    }
    return json.dumps(payload)


def test_provider_name_is_duckduckgo():
    """``provider_name`` exposes the canonical identifier."""
    assert DuckDuckGoProvider().provider_name == "duckduckgo"


def test_provider_returns_empty_on_error_envelope(monkeypatch):
    """When ``web_search`` returns an error envelope, the provider returns empty."""
    from src.tools import web_search as ws

    monkeypatch.setattr(ws, "web_search", lambda *a, **k: _envelope(error="boom"))

    provider = DuckDuckGoProvider()
    response = provider.search("anything")

    assert response.provider == "duckduckgo"
    assert response.results == []


def test_provider_parses_envelope_into_results(monkeypatch):
    """A valid envelope is mapped to SearchResult instances."""
    from src.tools import web_search as ws

    monkeypatch.setattr(
        ws,
        "web_search",
        lambda *a, **k: _envelope(
            results=[
                {
                    "title": "A",
                    "url": "https://a.com",
                    "published_at": "2026-06-20",
                    "body": "Snippet A",
                },
                {
                    "title": "B",
                    "url": "https://b.com",
                    "published_at": None,
                    "body": "Snippet B",
                },
            ]
        ),
    )

    response = DuckDuckGoProvider().search("q")

    assert response.provider == "duckduckgo"
    assert len(response.results) == 2
    assert response.results[0].url == "https://a.com"
    assert response.results[0].snippet == "Snippet A"
    assert response.results[0].rank == 1
    assert response.results[1].rank == 2


def test_provider_returns_empty_on_invalid_json(monkeypatch):
    """If the envelope cannot be parsed, an empty SearchResponse is returned."""
    from src.tools import web_search as ws

    monkeypatch.setattr(ws, "web_search", lambda *a, **k: "not json")

    response = DuckDuckGoProvider().search("anything")
    assert response.results == []
