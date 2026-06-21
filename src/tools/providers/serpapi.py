"""SerpApi search provider implementation."""

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

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"


def _time_range_to_serpapi(time_range: TimeRange) -> str | None:
    mapping = {"d": "d", "w": "w", "m": "m", "y": "y"}
    if time_range is None:
        return None
    return mapping.get(time_range)


class SerpApiProvider:
    """SearchProvider backed by SerpApi."""

    provider_name: str = "serpapi"

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self._api_key = api_key if api_key is not None else os.environ.get("SERPAPI_API_KEY")
        self._session = session or requests.Session()

    def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: TimeRange = None,
    ) -> SearchResponse:
        """Search via SerpApi and return a normalised ``SearchResponse``."""
        if not self._api_key:
            return empty_response(self.provider_name, query)

        params: dict[str, Any] = {
            "engine": "google",
            "q": query,
            "num": max_results,
            "api_key": self._api_key,
        }
        tbs = _time_range_to_serpapi(time_range)
        if tbs is not None:
            params["tbs"] = f"qdr:{tbs}"

        url = f"{SERPAPI_ENDPOINT}?{urlencode(params)}"

        try:
            response = self._session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception:
            return empty_response(self.provider_name, query)

        results: list[SearchResult] = []
        for index, item in enumerate(data.get("organic_results") or [], start=1):
            if not isinstance(item, dict):
                continue
            try:
                published_at = _parse_serpapi_date(item.get("date"))
                results.append(
                    SearchResult(
                        title=item.get("title", "") or "",
                        url=item.get("link", "") or "",
                        snippet=item.get("snippet", "") or "",
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
            raw=data if isinstance(data, dict) else None,
        )


def _parse_serpapi_date(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None
