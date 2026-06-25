"""Serper.dev search provider implementation."""

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

SERPER_ENDPOINT = "https://google.serper.dev/search"


def _time_range_to_serper(time_range: TimeRange) -> str | None:
    mapping = {"d": "d", "w": "w", "m": "m", "y": "y"}
    if time_range is None:
        return None
    return mapping.get(time_range)


class SerperProvider:
    """SearchProvider backed by Serper.dev (Google SERP)."""

    provider_name: str = "serper"

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self._api_key = api_key if api_key is not None else os.environ.get("SERPER_API_KEY")
        self._session = session or requests.Session()

    def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: TimeRange = None,
    ) -> SearchResponse:
        """Search via Serper and return a normalised ``SearchResponse``."""
        if not self._api_key:
            return empty_response(self.provider_name, query)

        payload: dict[str, Any] = {"q": query, "num": max_results}
        tbs = _time_range_to_serper(time_range)
        if tbs is not None:
            payload["tbs"] = f"qdr:{tbs}"

        headers = {
            "X-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }

        try:
            response = self._session.post(
                SERPER_ENDPOINT, json=payload, headers=headers, timeout=10
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            return empty_response(self.provider_name, query)

        results: list[SearchResult] = []
        for index, item in enumerate(data.get("organic") or [], start=1):
            if not isinstance(item, dict):
                continue
            try:
                published_at = _parse_serper_date(item.get("date"))
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
            retrieved_at=datetime.now(UTC),
            results=results,
            raw=data if isinstance(data, dict) else None,
        )


def _parse_serper_date(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None
