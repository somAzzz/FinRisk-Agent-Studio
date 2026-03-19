"""Web search tool using DuckDuckGo for fast RAG-style searches."""

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
