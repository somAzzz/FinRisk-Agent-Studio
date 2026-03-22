"""Web search tool using DuckDuckGo for fast RAG-style searches."""

import re
from datetime import datetime
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


def format_results(results: list[dict]) *********REMOVED********* str:
    """Format search results for LLM consumption."""
    if not results:
        return "No results found."

    formatted = []
    for i, r in enumerate(results, 1):
        formatted.append(
            f"Source [{i}]: {r['title']}\n"
            f"URL: {r['href']}\n"
            f"Summary: {r['body'][:300]}"
        )
    return "\n\n".join(formatted)


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


def web_search(query: str, max_results: int = 5) *********REMOVED********* str:
    """Execute web search and return formatted results.

    This is a fast, API-based search that returns clean text snippets
    suitable for RAG workflows. No browser automation needed.

    Args:
        query: Search query (English recommended)
        max_results: Number of results to return (default 5)

    Returns:
        Formatted string with search results for LLM consumption
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return "Error: ddgs package not installed. Run: uv pip install ddgs"

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return format_results(results)
    except Exception as e:
        return f"Search failed: {str(e)}"


# Tool definition for LLM tool calling
WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": "Fast web search using DuckDuckGo. Returns formatted text snippets from search results. Best for quick factual queries, news, and general web information. Use when you need current events info or quick answers.",
    "input_schema": WebSearchInput.model_json_schema(),
}
