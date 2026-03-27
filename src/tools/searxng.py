"""SearXNG transparent fallback search (LLM不可见).

This module provides a fallback search when ddgs fails.
It is NOT exposed to the LLM router - used transparently in try-except.
"""

import json
import os
from datetime import datetime, timezone
from typing import Literal

import httpx


def searxng_search(
    query: str,
    time_range: Literal["d", "w", "m", "y", None] = None,
) -> str:
    """Execute SearXNG search and return unified JSON Envelope.

    SearXNG aggregates multiple search engines (Google, Bing, DuckDuckGo).
    Used transparently when ddgs fails - LLM is unaware of this fallback.

    Args:
        query: Search query
        time_range: Time filter - 'd'=day, 'w'=week, 'm'=month, 'y'=year

    Returns:
        JSON Envelope string with search results
    """
    searxng_url = os.environ.get("SEARXNG_URL", "https://search.example.com")

    try:
        response = httpx.get(
            f"{searxng_url}/search",
            params={
                "q": query,
                "format": "json",
                "engines": "google,bing,duckduckgo",
                "time_range": time_range,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        results = response.json()

        return json.dumps({
            "source": "searxng",
            "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query_used": query,
            "time_range_applied": time_range,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "published_at": r.get("publishedDate"),
                    "body": r.get("content", "")[:300],
                }
                for r in results.get("results", [])[:5]
            ],
        }, ensure_ascii=False)

    except (httpx.HTTPError, httpx.TimeoutException, json.JSONDecodeError) as e:
        return json.dumps({
            "source": "searxng",
            "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query_used": query,
            "error": str(e),
            "results": [],
        })