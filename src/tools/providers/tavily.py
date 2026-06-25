"""Tavily search provider implementation."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import requests

from src.tools.providers.base import (
    SearchResponse,
    SearchResult,
    TimeRange,
    empty_response,
)

TAVILY_ENDPOINT = "https://api.tavily.com/search"


class TavilyProvider:
    """SearchProvider backed by Tavily's ``/search`` endpoint."""

    provider_name: str = "tavily"

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self._api_key = api_key if api_key is not None else os.environ.get("TAVILY_API_KEY")
        self._session = session or requests.Session()

    def is_available(self) -> bool:
        """Tavily is reachable only when an API key has been configured."""
        return bool(self._api_key)

    def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: TimeRange = None,
    ) -> SearchResponse:
        """Search Tavily and return a normalised ``SearchResponse``."""
        if not self._api_key:
            return empty_response(self.provider_name, query)

        payload: dict[str, Any] = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        if time_range is not None:
            payload["time_range"] = _time_range_to_tavily(time_range)

        try:
            response = self._session.post(TAVILY_ENDPOINT, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception:
            return empty_response(self.provider_name, query)

        results: list[SearchResult] = []
        for index, item in enumerate(data.get("results") or [], start=1):
            if not isinstance(item, dict):
                continue
            try:
                published_at = _parse_tavily_date(item.get("published_date"))
                results.append(
                    SearchResult(
                        title=item.get("title", "") or "",
                        url=item.get("url", "") or "",
                        snippet=item.get("content", "") or "",
                        published_at=published_at,
                        source=self.provider_name,
                        rank=index,
                        metadata={
                            "score": item.get("score"),
                            "provider": self.provider_name,
                        },
                    )
                )
            except Exception:
                continue

        return SearchResponse(
            provider=self.provider_name,
            query=query,
            retrieved_at=datetime.now(UTC),
            results=results,
            raw=data if isinstance(data, dict) else None,
        )


def _time_range_to_tavily(time_range: TimeRange) -> str:
    mapping = {"d": "day", "w": "week", "m": "month", "y": "year"}
    return mapping.get(time_range or "", "week")


def _parse_tavily_date(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None
