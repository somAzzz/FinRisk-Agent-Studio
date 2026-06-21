"""Brave Search provider implementation."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import requests

from src.tools.providers.base import (
    SearchResponse,
    SearchResult,
    TimeRange,
    empty_response,
)

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


def _time_range_to_brave(time_range: TimeRange) -> str | None:
    mapping = {"d": "pd", "w": "pw", "m": "pm", "y": "py"}
    if time_range is None:
        return None
    return mapping.get(time_range)


class BraveProvider:
    """SearchProvider backed by the Brave Search API."""

    provider_name: str = "brave"

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self._api_key = api_key if api_key is not None else os.environ.get("BRAVE_API_KEY")
        self._session = session or requests.Session()

    def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: TimeRange = None,
    ) -> SearchResponse:
        """Search Brave and return a normalised ``SearchResponse``."""
        if not self._api_key:
            return empty_response(self.provider_name, query)

        params: dict[str, Any] = {"q": query, "count": max_results}
        freshness = _time_range_to_brave(time_range)
        if freshness is not None:
            params["freshness"] = freshness

        url = f"{BRAVE_ENDPOINT}?{urlencode(params)}"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }

        try:
            response = self._session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return empty_response(self.provider_name, query)

        results: list[SearchResult] = []
        for index, item in enumerate((payload.get("web") or {}).get("results") or [], start=1):
            if not isinstance(item, dict):
                continue
            try:
                published_at = _parse_brave_age(item.get("age"))
                results.append(
                    SearchResult(
                        title=item.get("title", "") or "",
                        url=item.get("url", "") or "",
                        snippet=item.get("description", "") or "",
                        published_at=published_at,
                        source=self.provider_name,
                        rank=index,
                        metadata={},
                    )
                )
            except Exception:
                continue

        return SearchResponse(
            provider=self.provider_name,
            query=query,
            retrieved_at=datetime.utcnow(),
            results=results,
            raw=payload if isinstance(payload, dict) else None,
        )


def _parse_brave_age(age: str | None) -> datetime | None:
    """Best-effort parse of Brave's ``age`` string (e.g. '2 days ago')."""
    if not age or not isinstance(age, str):
        return None
    # Brave returns a free-form string; we don't attempt full parsing.
    return None
