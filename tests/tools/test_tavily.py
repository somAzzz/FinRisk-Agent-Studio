import json
import os
import pytest
import httpx
from unittest.mock import patch, MagicMock

from tools.tavily import tavily_search


def test_tavily_search_returns_unified_envelope():
    """Tavily should return JSON Envelope with source='tavily'."""
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            json=lambda: {
                "results": [
                    {"title": "Test", "url": "https://test.com", "content": "Test content", "published_date": "2026-03-20"}
                ],
                "answer": "Test answer"
            }
        )
        mock_post.return_value.raise_for_status = MagicMock()
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            result = tavily_search("test query")
            data = json.loads(result)
            assert data["source"] == "tavily"
            assert data["query_used"] == "test query"
            assert len(data["results"]) == 1
            assert data["results"][0]["body"] == "Test content"


def test_tavily_search_missing_api_key():
    """Tavily should return error when TAVILY_API_KEY is not set."""
    env = os.environ.copy()
    env.pop("TAVILY_API_KEY", None)
    with patch.dict(os.environ, env, clear=True):
        result = tavily_search("test query")
        data = json.loads(result)
        assert data["source"] == "tavily"
        assert data["error"] == "TAVILY_API_KEY not set"
        assert data["results"] == []


def test_tavily_search_http_error():
    """Tavily should handle HTTP errors gracefully."""
    with patch("httpx.post") as mock_post:
        mock_post.side_effect = httpx.HTTPError("404 Client Error")
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            result = tavily_search("test query")
            data = json.loads(result)
            assert data["source"] == "tavily"
            assert "HTTP error" in data["error"]
            assert data["results"] == []


def test_tavily_search_empty_results():
    """Tavily should handle empty results array."""
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            json=lambda: {"results": [], "answer": None}
        )
        mock_post.return_value.raise_for_status = MagicMock()
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            result = tavily_search("test query")
            data = json.loads(result)
            assert data["source"] == "tavily"
            assert data["results"] == []
            assert data["answer"] is None


def test_tavily_search_max_results_limit():
    """Tavily should limit results to max_results parameter."""
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            json=lambda: {
                "results": [
                    {"title": f"Result {i}", "url": f"https://test.com/{i}", "content": f"Content {i}", "published_date": "2026-03-20"}
                    for i in range(20)
                ],
                "answer": "Test answer"
            }
        )
        mock_post.return_value.raise_for_status = MagicMock()
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            result = tavily_search("test query", max_results=5)
            data = json.loads(result)
            assert data["source"] == "tavily"
            assert len(data["results"]) == 5


def test_tavily_search_json_decode_error():
    """Tavily should handle JSON decode errors gracefully."""
    with patch("httpx.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            result = tavily_search("test query")
            data = json.loads(result)
            assert data["source"] == "tavily"
            assert "JSON decode error" in data["error"]
            assert data["results"] == []
