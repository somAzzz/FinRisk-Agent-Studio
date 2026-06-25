"""DuckDuckGo provider — wraps the existing ``web_search`` function."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.tools.providers.base import (
    SearchResponse,
    SearchResult,
    TimeRange,
    empty_response,
)


class DuckDuckGoProvider:
    """SearchProvider backed by the existing ``src.tools.web_search`` helper."""

    provider_name: str = "duckduckgo"

    def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: TimeRange = None,
    ) -> SearchResponse:
        """Search via DuckDuckGo and parse the JSON envelope."""
        # Local import so the providers package stays decoupled from
        # web_search's optional dependency on ``ddgs``/``duckduckgo_search``.
        from src.tools.web_search import web_search

        try:
            raw_output: str = web_search(query, max_results, time_range)
        except Exception:
            return empty_response(self.provider_name, query)

        try:
            data: dict[str, Any] = json.loads(raw_output)
        except (TypeError, ValueError):
            return empty_response(self.provider_name, query)

        if not isinstance(data, dict):
            return empty_response(self.provider_name, query)

        if "error" in data:
            return empty_response(self.provider_name, query)

        raw_results = data.get("results") or []
        results: list[SearchResult] = []
        for index, item in enumerate(raw_results, start=1):
            if not isinstance(item, dict):
                continue
            try:
                published_raw = item.get("published_at")
                published_at: datetime | None = None
                if isinstance(published_raw, str) and published_raw:
                    try:
                        published_at = datetime.strptime(
                            published_raw[:10], "%Y-%m-%d"
                        )
                    except ValueError:
                        published_at = None

                snippet = item.get("body", "") or item.get("snippet", "")
                title = item.get("title", "") or ""
                url = item.get("url", "") or item.get("href", "") or ""

                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        published_at=published_at,
                        source=self.provider_name,
                        rank=index,
                        metadata={},
                    )
                )
            except Exception:
                # Skip malformed individual entries but keep the rest.
                continue

        retrieved_raw = data.get("retrieved_at")
        retrieved_at = datetime.now(timezone.utc)
        if isinstance(retrieved_raw, str) and retrieved_raw:
            try:
                retrieved_at = datetime.strptime(
                    retrieved_raw.rstrip("Z")[:19], "%Y-%m-%dT%H:%M:%S"
                )
            except ValueError:
                retrieved_at = datetime.now(timezone.utc)

        return SearchResponse(
            provider=self.provider_name,
            query=data.get("query_used", query),
            retrieved_at=retrieved_at,
            results=results,
            raw=data,
        )
