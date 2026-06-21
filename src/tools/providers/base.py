"""Base abstractions and schemas for search providers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

SearchIntent = Literal[
    "general",
    "news",
    "sec",
    "ir",
    "transcript",
    "semantic",
    "agent_research",
    "verification",
]

TimeRange = Literal["d", "w", "m", "y", None]


class SearchResult(BaseModel):
    """A single normalised search result."""

    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    snippet: str = ""
    published_at: datetime | None = None
    source: str | None = None
    rank: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """A normalised envelope returned by all search providers."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    query: str
    retrieved_at: datetime
    results: list[SearchResult] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


@runtime_checkable
class SearchProvider(Protocol):
    """Protocol every search provider must implement."""

    provider_name: str

    def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: TimeRange = None,
    ) -> SearchResponse:
        """Run a search and return a normalised ``SearchResponse``."""


def empty_response(provider: str, query: str) -> SearchResponse:
    """Return an empty :class:`SearchResponse` for a provider."""
    return SearchResponse(
        provider=provider,
        query=query,
        retrieved_at=datetime.now(UTC),
        results=[],
        raw=None,
    )
