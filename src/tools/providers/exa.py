"""Exa search provider implementation."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import requests

from src.tools.providers.base import (
    SearchResponse,
    SearchResult,
    TimeRange,
    empty_response,
)

EXA_ENDPOINT = "https://api.exa.ai/search"


class ExaProvider:
    """SearchProvider backed by Exa's neural search endpoint."""

    provider_name: str = "exa"

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self._api_key = api_key if api_key is not None else os.environ.get("EXA_API_KEY")
        self._session = session or requests.Session()

    def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: TimeRange = None,
    ) -> SearchResponse:
        """Search Exa and return a normalised ``SearchResponse``."""
        if not self._api_key:
            return empty_response(self.provider_name, query)

        payload: dict[str, Any] = {
            "query": query,
            "numResults": max_results,
        }
        if time_range is not None:
            payload["startPublishedDate"] = _time_range_to_exa(time_range)

        headers = {
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        try:
            response = self._session.post(
                EXA_ENDPOINT, json=payload, headers=headers, timeout=10
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            return empty_response(self.provider_name, query)

        results: list[SearchResult] = []
        for index, item in enumerate(data.get("results") or [], start=1):
            if not isinstance(item, dict):
                continue
            try:
                published_at = _parse_iso_date(item.get("publishedDate"))
                results.append(
                    SearchResult(
                        title=item.get("title", "") or "",
                        url=item.get("url", "") or "",
                        snippet=item.get("text", "") or item.get("snippet", "") or "",
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


def _time_range_to_exa(time_range: TimeRange) -> str:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    mapping = {"d": 1, "w": 7, "m": 30, "y": 365}
    days = mapping.get(time_range or "", 7)
    return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_date(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:19].rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
