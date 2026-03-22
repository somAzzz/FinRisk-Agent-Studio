"""Web search tool using DuckDuckGo for fast RAG-style searches."""

import json
import re
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Literal


class SearchResult(BaseModel):
    """Single search result."""
    title: str
    url: str
    body: str


class WebSearchInput(BaseModel):
    """Input for web search tool."""
    query: str = Field(description="Search query in English for best results")
    max_results: int = Field(default=5, description="Maximum number of results to return")
    time_range: Literal["d", "w", "m", "y", None] = Field(
        default=None, description="Time filter - 'd'=day, 'w'=week, 'm'=month, 'y'=year"
    )


def _extract_published_date(result: dict) *********REMOVED********* str | None:
    """Extract publication date from DDGS result.

    Try to extract date from:
    1. result['date'] if present
    2. Regex match in result['body'] for date patterns like "Mar 15, 2026"
    3. Return None if no date found
    """
    # Try direct date field first
    if result.get("date"):
        return result["date"]

    # Try regex patterns in body
    date_patterns = [
        r"(\w{3,9}\s+\d{1,2},?\s+\d{4})",  # "March 15, 2026" or "March 15 2026"
        r"(\d{4}-\d{2}-\d{2})",  # "2026-03-15"
        r"(\d{1,2}\s+\w{3,9}\s+\d{4})",  # "15 March 2026"
    ]
    for pattern in date_patterns:
        match = re.search(pattern, result.get("body", ""))
        if match:
            date_str = match.group(1)
            # Try formats in order: without comma first (more specific)
            for fmt in ("%B %d %Y", "%B %d, %Y", "%b %d %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(date_str, fmt)
                    return parsed.strftime("%Y-%m-%d")
                except ValueError:
                    pass
    return None


def _format_search_output(
    results: list[dict],
    query: str,
    time_range: Literal["d", "w", "m", "y", None] = None,
) *********REMOVED********* str:
    """Format search results as JSON Envelope for reliable LLM parsing.

    JSON Envelope structure:
    {
        "retrieved_at": "2026-03-22T14:30:00Z",  # UTC timestamp
        "query_used": "...",
        "time_range_applied": "m" | null,
        "results": [
            {"title": "...", "url": "...", "published_at": "...", "body": "..."},
            ...
        ]
    }
    """
    if not results:
        return json.dumps({
            "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query_used": query,
            "time_range_applied": time_range,
            "results": []
        }, ensure_ascii=False)

    output = {
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "query_used": query,
        "time_range_applied": time_range,
        "results": []
    }

    for r in results:
        output["results"].append({
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "published_at": _extract_published_date(r),
            "body": r.get("body", "")[:300]
        })

    return json.dumps(output, ensure_ascii=False)


def web_search(
    query: str,
    max_results: int = 5,
    time_range: Literal["d", "w", "m", "y", None] = None,
) *********REMOVED********* str:
    """Execute web search and return JSON Envelope.

    Args:
        query: Search query (English recommended)
        max_results: Number of results to return (default 5)
        time_range: Time filter - 'd'=day, 'w'=week, 'm'=month, 'y'=year, None=no filter

    Returns:
        JSON Envelope string with search results
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return json.dumps({"error": "ddgs package not installed. Run: uv pip install ddgs"})

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, timelimit=time_range))
            return _format_search_output(results, query, time_range)
    except Exception as e:
        return json.dumps({"error": f"Search failed: {str(e)}"})


# Tool definition for LLM tool calling
WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": "Fast web search using DuckDuckGo. Returns formatted text snippets from search results. Best for quick factual queries, news, and general web information. Use when you need current events info or quick answers.",
    "input_schema": WebSearchInput.model_json_schema(),
}
