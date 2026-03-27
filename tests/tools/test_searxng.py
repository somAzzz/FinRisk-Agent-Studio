import json
import pytest
from unittest.mock import patch, MagicMock

import httpx

from tools.searxng import searxng_search


def test_searxng_returns_unified_envelope():
    """SearXNG should return JSON Envelope with source='searxng'."""
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            json=lambda: {
                "results": [
                    {
                        "title": "Test",
                        "url": "https://test.com",
                        "content": "Test content",
                        "publishedDate": "2026-03-20",
                    }
                ]
            }
        )

        result = searxng_search("test query")

        data = json.loads(result)
        assert data["source"] == "searxng"
        assert data["query_used"] == "test query"


def test_searxng_empty_results():
    """SearXNG should return empty results list when no results found."""
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            json=lambda: {"results": []},
            raise_for_status=MagicMock(),
        )

        result = searxng_search("empty query")
        data = json.loads(result)

        assert data["source"] == "searxng"
        assert data["results"] == []


def test_searxng_time_range_parameter():
    """SearXNG should pass time_range parameter to the API."""
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            json=lambda: {"results": []},
            raise_for_status=MagicMock(),
        )

        searxng_search("test query", time_range="w")
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"]["time_range"] == "w"


def test_searxng_http_error_handling():
    """SearXNG should handle HTTP errors gracefully."""
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(
                side_effect=httpx.HTTPError("HTTP 500")
            )
        )

        result = searxng_search("test query")
        data = json.loads(result)

        assert data["source"] == "searxng"
        assert "error" in data
        assert data["results"] == []


def test_searxng_timeout_error_handling():
    """SearXNG should handle timeout errors gracefully."""
    with patch("httpx.get") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Request timeout")

        result = searxng_search("test query")
        data = json.loads(result)

        assert data["source"] == "searxng"
        assert "error" in data
        assert data["results"] == []


def test_searxng_json_decode_error_handling():
    """SearXNG should handle JSON decode errors gracefully."""
    with patch("httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError(
            "Invalid JSON", "", 0
        )
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = searxng_search("test query")
        data = json.loads(result)

        assert data["source"] == "searxng"
        assert "error" in data
        assert data["results"] == []
