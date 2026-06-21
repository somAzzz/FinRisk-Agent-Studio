"""SQLite-backed cache for normalised search responses.

Uses only the Python standard library so it works in any environment.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.tools.providers.base import SearchResponse, TimeRange

DEFAULT_TTL_SECONDS = 3600


class SearchCache:
    """SQLite-backed key/value cache for :class:`SearchResponse` objects."""

    def __init__(self, cache_dir: Path | str = ".cache/fintext_llm", db_name: str = "search_cache.sqlite"):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._cache_dir / db_name
        self._lock = threading.Lock()
        self._ensure_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS search_cache (
                        key TEXT PRIMARY KEY,
                        provider TEXT NOT NULL,
                        query TEXT NOT NULL,
                        response_json TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        ttl_seconds INTEGER NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_search_cache_expiry
                    ON search_cache(created_at, ttl_seconds)
                    """
                )
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def make_key(
        provider: str,
        query: str,
        max_results: int = 5,
        time_range: TimeRange = None,
        intent: str = "general",
    ) -> str:
        """Build a deterministic cache key from search parameters."""
        payload = json.dumps(
            {
                "provider": provider,
                "query": query,
                "max_results": max_results,
                "time_range": time_range,
                "intent": intent,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(
        self,
        provider: str,
        query: str,
        params_hash: str,
        max_results: int = 5,
        time_range: TimeRange = None,
        intent: str = "general",
    ) -> SearchResponse | None:
        """Return the cached response for ``provider``/``query`` if fresh."""
        key = self.make_key(provider, query, max_results, time_range, intent)
        if key != params_hash:
            # Caller supplied a custom hash that does not match ours;
            # fall back to the standard key derived from the parameters.
            key = params_hash

        now_ts = int(datetime.now(UTC).timestamp())
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT response_json, created_at, ttl_seconds "
                    "FROM search_cache WHERE key = ?",
                    (key,),
                ).fetchone()
            finally:
                conn.close()

        if row is None:
            return None

        expires_at = int(row["created_at"]) + int(row["ttl_seconds"])
        if expires_at < now_ts:
            # Expired; treat as miss and prune.
            self._delete(key)
            return None

        try:
            data: dict[str, Any] = json.loads(row["response_json"])
        except (TypeError, ValueError):
            return None

        try:
            return SearchResponse.model_validate(data)
        except Exception:
            return None

    def set(
        self,
        response: SearchResponse,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        provider: str | None = None,
        query: str | None = None,
        max_results: int = 5,
        time_range: TimeRange = None,
        intent: str = "general",
    ) -> None:
        """Persist ``response`` using a key derived from its parameters."""
        provider_name = provider or response.provider
        query_text = query or response.query
        key = self.make_key(provider_name, query_text, max_results, time_range, intent)
        payload = response.model_dump(mode="json")
        created_at = int(datetime.now(UTC).timestamp())

        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO search_cache (
                        key, provider, query, response_json, created_at, ttl_seconds
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        response_json = excluded.response_json,
                        created_at = excluded.created_at,
                        ttl_seconds = excluded.ttl_seconds
                    """,
                    (
                        key,
                        provider_name,
                        query_text,
                        json.dumps(payload, ensure_ascii=False),
                        created_at,
                        ttl_seconds,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def _delete(self, key: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM search_cache WHERE key = ?", (key,))
                conn.commit()
            finally:
                conn.close()

    def clear(self) -> None:
        """Remove all entries (used by tests)."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM search_cache")
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def ttl_for(ttl_seconds: int) -> timedelta:
        """Helper to convert ``ttl_seconds`` into a ``timedelta``."""
        return timedelta(seconds=ttl_seconds)
