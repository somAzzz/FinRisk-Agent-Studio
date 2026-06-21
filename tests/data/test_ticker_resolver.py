"""Tests for the ticker -> CIK resolver.

The resolver never raises. Tests cover three data sources in priority
order: in-memory cache, on-disk cache, and the built-in fixture table.
The SEC endpoint is monkeypatched out so tests never hit the network.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.data.ticker_resolver import CompanyIdentifier, TickerResolver


class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


def _fake_session(payload: dict, status_code: int = 200):
    captured: dict = {}

    def fake_get(url, timeout=None, headers=None):  # noqa: ARG001
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse(payload, status_code)

    fake = SimpleNamespace(get=fake_get)
    return fake, captured


def test_resolve_from_fallback_returns_aapl_cik(tmp_path: Path) -> None:
    """``AAPL`` is in the built-in fixture table."""
    resolver = TickerResolver(cache_path=tmp_path / "ticker_cache.json")
    ident = resolver.resolve("AAPL")
    assert isinstance(ident, CompanyIdentifier)
    assert ident.ticker == "AAPL"
    assert ident.cik == "0000320193"
    assert ident.name == "Apple Inc."


def test_resolve_is_case_insensitive(tmp_path: Path) -> None:
    resolver = TickerResolver(cache_path=tmp_path / "ticker_cache.json")
    ident = resolver.resolve("aapl")
    assert ident is not None
    assert ident.cik == "0000320193"


def test_resolve_returns_none_for_unknown_ticker(tmp_path: Path) -> None:
    resolver = TickerResolver(cache_path=tmp_path / "ticker_cache.json")
    assert resolver.resolve("ZZZZ") is None


def test_resolve_returns_none_for_empty_ticker(tmp_path: Path) -> None:
    resolver = TickerResolver(cache_path=tmp_path / "ticker_cache.json")
    assert resolver.resolve("") is None


def test_resolve_persists_to_disk_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A SEC fetch result is written to the on-disk cache."""
    payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
    }
    session, captured = _fake_session(payload)
    cache = tmp_path / "ticker_cache.json"
    resolver = TickerResolver(cache_path=cache, session=session)
    ident = resolver.resolve("AAPL")
    assert ident is not None
    assert ident.cik == "0000320193"
    assert cache.is_file()
    # Re-instantiating should hit the disk cache.
    resolver2 = TickerResolver(cache_path=cache)
    ident2 = resolver2.resolve("AAPL")
    assert ident2 is not None
    assert ident2.cik == "0000320193"


def test_resolve_loads_from_existing_disk_cache(tmp_path: Path) -> None:
    cache = tmp_path / "ticker_cache.json"
    cache.write_text(
        '{"AAPL": {"ticker": "AAPL", "cik": "0000320193", "name": null}}',
        encoding="utf-8",
    )
    resolver = TickerResolver(cache_path=cache)
    ident = resolver.resolve("AAPL")
    assert ident is not None
    assert ident.cik == "0000320193"
    assert ident.name is None


def test_resolve_handles_corrupt_disk_cache(tmp_path: Path) -> None:
    cache = tmp_path / "ticker_cache.json"
    cache.write_text("{not valid json", encoding="utf-8")
    resolver = TickerResolver(cache_path=cache)
    # Falls through to fallback fixture for AAPL.
    ident = resolver.resolve("AAPL")
    assert ident is not None
    assert ident.cik == "0000320193"


def test_resolve_handles_non_200_from_sec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload: dict = {}
    session, _ = _fake_session(payload, status_code=503)
    resolver = TickerResolver(
        cache_path=tmp_path / "ticker_cache.json", session=session
    )
    # SEC unavailable -> fallback fixture kicks in for AAPL.
    assert resolver.resolve("AAPL").cik == "0000320193"


def test_resolve_returns_none_when_sec_payload_has_no_match(
    tmp_path: Path,
) -> None:
    """When the SEC JSON has no match and the ticker is not in the fallback
    table, ``resolve`` returns ``None``.
    """
    payload = {
        "0": {"cik_str": 999999, "ticker": "ZZZZ", "title": "Z Co"}
    }
    session, _ = _fake_session(payload)
    resolver = TickerResolver(
        cache_path=tmp_path / "ticker_cache.json", session=session
    )
    assert resolver.resolve("ZZZZ-OTHER") is None
