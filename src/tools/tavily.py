"""Tavily deep search tool for LLM-optimized RAG."""

import httpx
import json
import os
from datetime import datetime, timezone
from typing import Literal


def tavily_search(
    query: str,
    max_results: int = 10,
    time_range: Literal["d", "w", "m", "y", None] = None,
) -> str:
    """Execute Tavily deep search and return unified JSON Envelope.

    Tavily provides longer summaries (500 chars) optimized for RAG,
    reducing the need for additional web_fetch calls.

    Args:
        query: Search query
        max_results: Number of results (default 10)
        time_range: Time filter - 'd'=day, 'w'=week, 'm'=month, 'y'=year

    Returns:
        JSON Envelope string with search results
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return json.dumps({
            "source": "tavily",
            "error": "TAVILY_API_KEY not set",
            "results": [],
        })

    try:
        response = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "time_range": time_range,
                "include_answer": True,
                "include_raw_content": False,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        return json.dumps({
            "source": "tavily",
            "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query_used": query,
            "time_range_applied": time_range,
            "answer": data.get("answer"),
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "published_at": r.get("published_date"),
                    "body": r.get("content", "")[:500],
                }
                for r in data.get("results", [])[:max_results]
            ],
        }, ensure_ascii=False)

    except httpx.HTTPError as e:
        return json.dumps({
            "source": "tavily",
            "error": f"HTTP error: {e}",
            "results": [],
        })
    except json.JSONDecodeError as e:
        return json.dumps({
            "source": "tavily",
            "error": f"JSON decode error: {e}",
            "results": [],
        })


TAVILY_TOOL = {
    "name": "tavily",
    "description": "Deep web search optimized for LLM RAG. Use for analysis, comprehensive reports, multi-source news, and trend research. Returns longer summaries (500 chars) to reduce web_fetch calls.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query in English"},
            "max_results": {"type": "integer", "default": 10},
            "time_range": {"type": "string", "enum": ["d", "w", "m", "y"], "description": "Time filter"},
        },
        "required": ["query"],
    },
}