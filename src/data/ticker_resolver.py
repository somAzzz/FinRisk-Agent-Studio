"""Ticker -> CIK resolver.

The SEC's public submissions endpoint requires a CIK, but users typically
hand us a ticker symbol. :class:`TickerResolver` bridges the two by
preferring (in order):

1. a local cache of previously resolved identifiers,
2. the SEC company tickers JSON (``data.sec.gov``), and
3. a small built-in fixture for the most common tickers used in tests.

The resolver never raises — every failure path returns ``None`` so the
caller can fall back to whatever the rest of the pipeline offers.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import requests
from pydantic import BaseModel, ConfigDict

from src.config import get_settings

# Public SEC endpoint mapping tickers to CIKs.
_SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# A tiny fallback table so the offline demo and unit tests can resolve
# the most common tickers without any network access. Keys are uppercase
# tickers; values are 10-digit zero-padded CIKs.
_FALLBACK_TICKERS: dict[str, tuple[str, str]] = {
    "AAPL": ("0000320193", "Apple Inc."),
    "MSFT": ("0000789019", "Microsoft Corporation"),
    "GOOGL": ("0001652044", "Alphabet Inc."),
    "AMZN": ("0001018724", "Amazon.com, Inc."),
    "NVDA": ("0001045810", "NVIDIA Corporation"),
    "META": ("0001326801", "Meta Platforms, Inc."),
    "TSLA": ("0001318605", "Tesla, Inc."),
    "DEMO": ("9999999999", "Demo Company, Inc."),
}


class CompanyIdentifier(BaseModel):
    """A canonical mapping from a ticker symbol to a CIK."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    cik: str
    name: str | None = None
    source: Literal["cache", "sec", "fallback"] = "fallback"
    resolved_at: datetime | None = None


class TickerResolver:
    """Resolve ticker symbols to SEC CIKs.

    Args:
        cache_path: Optional path to a local JSON cache. When omitted, a
            ``ticker_cache.json`` under ``Settings.cache_dir`` is used.
        session: Optional ``requests.Session`` (mainly for tests).
    """

    def __init__(
        self,
        cache_path: Path | None = None,
        session: requests.Session | None = None,
        timeout: float = 20.0,
    ) -> None:
        if cache_path is None:
            cache_path = get_settings().cache_dir / "ticker_cache.json"
        self.cache_path: Path = Path(cache_path)
        self.timeout = timeout
        self._session = session or requests.Session()
        self._memory_cache: dict[str, CompanyIdentifier] = {}

    def resolve(self, ticker: str) -> CompanyIdentifier | None:
        """Return a :class:`CompanyIdentifier` for ``ticker`` or ``None``.

        The lookup order is in-memory cache, on-disk cache, SEC endpoint,
        then the built-in fixture table. Each returned identifier carries
        a ``source`` tag (``"cache"`` / ``"sec"`` / ``"fallback"``) and a
        ``resolved_at`` timestamp so downstream callers can audit provenance.
        """
        key = ticker.upper().strip()
        if not key:
            return None

        if key in self._memory_cache:
            return self._memory_cache[key]

        ident = self._load_from_disk(key)
        if ident is not None:
            # Older cache rows may have ``source == "fallback"``; upgrade
            # the tag so consumers can trust the disk-cache provenance.
            if ident.source != "cache":
                ident = ident.model_copy(
                    update={
                        "source": "cache",
                        "resolved_at": datetime.now(tz=UTC),
                    }
                )
                self._memory_cache[key] = ident
            else:
                self._memory_cache[key] = ident
            return ident

        ident = self._fetch_from_sec(key)
        if ident is not None:
            ident = ident.model_copy(
                update={"resolved_at": datetime.now(tz=UTC)}
            )
            self._memory_cache[key] = ident
            self._persist_to_disk(ident)
            return ident

        ident = self._load_from_fallback(key)
        if ident is not None:
            self._memory_cache[key] = ident
        return ident

    # -- cache helpers ---------------------------------------------------
    def _load_from_disk(self, key: str) -> CompanyIdentifier | None:
        if not self.cache_path.is_file():
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        raw = payload.get(key)
        if not isinstance(raw, dict):
            return None
        # Older cache rows may not have source / resolved_at; backfill so
        # the schema stays strict.
        if "source" not in raw:
            raw["source"] = "cache"
        if "resolved_at" not in raw:
            raw["resolved_at"] = datetime.now(tz=UTC).isoformat()
        try:
            return CompanyIdentifier.model_validate(raw)
        except Exception:
            return None

    def _persist_to_disk(self, ident: CompanyIdentifier) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            existing: dict[str, Any] = {}
            if self.cache_path.is_file():
                try:
                    payload = json.loads(
                        self.cache_path.read_text(encoding="utf-8")
                    )
                    if isinstance(payload, dict):
                        existing = payload
                except (OSError, json.JSONDecodeError):
                    existing = {}
            # ``resolved_at`` is a datetime; ``model_dump(mode="json")`` keeps
            # the JSON encoder happy.
            existing[ident.ticker.upper()] = ident.model_dump(mode="json")
            self.cache_path.write_text(
                json.dumps(existing, indent=2), encoding="utf-8"
            )
        except OSError:
            # Cache writes are best-effort; ignore disk failures.
            return

    # -- SEC endpoint ----------------------------------------------------
    def _fetch_from_sec(self, key: str) -> CompanyIdentifier | None:
        try:
            response = self._session.get(
                _SEC_TICKERS_URL,
                timeout=self.timeout,
                headers={
                    "User-Agent": get_settings().sec_user_agent,
                    "Accept": "application/json",
                },
            )
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        # SEC format: { "0": {"cik_str": 320193, "ticker": "AAPL",
        # "title": "Apple Inc."}, ... }
        for entry in payload.values():
            if not isinstance(entry, dict):
                continue
            entry_ticker = str(entry.get("ticker", "")).upper()
            if entry_ticker != key:
                continue
            raw_cik = entry.get("cik_str")
            if raw_cik is None:
                continue
            try:
                cik_int = int(raw_cik)
            except (TypeError, ValueError):
                continue
            return CompanyIdentifier(
                ticker=key,
                cik=str(cik_int).zfill(10),
                name=str(entry.get("title")) or None,
                source="sec",
                resolved_at=datetime.now(tz=UTC),
            )
        return None

    # -- fixture fallback -----------------------------------------------
    @staticmethod
    def _load_from_fallback(key: str) -> CompanyIdentifier | None:
        entry = _FALLBACK_TICKERS.get(key)
        if entry is None:
            return None
        cik, name = entry
        return CompanyIdentifier(
            ticker=key,
            cik=cik,
            name=name,
            source="fallback",
            resolved_at=datetime.now(tz=UTC),
        )


__all__ = ["CompanyIdentifier", "TickerResolver"]
