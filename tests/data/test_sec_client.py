"""Tests for :mod:`src.data.sec_client`.

These tests never hit the real SEC network. ``requests.Session.get`` is
monkeypatched with a small fake response object whose ``status_code`` and
``json()`` / ``text`` are configurable per test.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from src.data.sec_client import (
    SECClient,
    SECClientError,
    SECHTTPError,
    SECNotFoundError,
    SECRateLimitError,
)


class FakeResponse:
    """Minimal stand-in for ``requests.Response`` used by the fakes below."""

    def __init__(
        self,
        status_code: int = 200,
        json_payload: Any | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_payload = json_payload if json_payload is not None else {}
        self.text = text

    def json(self) -> Any:
        return self._json_payload


def _patch_session_get(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeResponse,
    captured: dict[str, Any],
):
    """Replace ``SECClient._session.get`` with a capturing stub."""

    def fake_get(*args: Any, **kwargs: Any) -> FakeResponse:
        # When ``fake_get`` is bound as a method, the first positional arg is
        # ``self`` (the Session instance); the URL is the second positional
        # arg or the ``url`` keyword arg.
        url = ""
        if len(args) >= 2:
            url = args[1]
        elif "url" in kwargs:
            url = kwargs["url"]
        captured["url"] = url
        captured["timeout"] = kwargs.get("timeout")
        captured["calls"] = captured.get("calls", 0) + 1
        return response

    monkeypatch.setattr(
        "src.data.sec_client.requests.Session.get", fake_get
    )


def test_user_agent_header_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """``SECClient`` must always send the User-Agent header."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(200, {}), captured)
    client = SECClient(user_agent="Research Bot research@example.com")
    headers = client.session.headers
    assert headers["User-Agent"] == "Research Bot research@example.com"
    # Calling get_submissions forces a request and exercises the session.
    client.get_submissions("0000320193")
    assert captured.get("calls") == 1


def test_pad_cik_zero_pads_to_ten_digits() -> None:
    """``pad_cik`` always returns a 10-character zero-padded string."""
    assert SECClient.pad_cik("320193") == "0000320193"
    assert SECClient.pad_cik("0000320193") == "0000320193"
    assert SECClient.pad_cik("1") == "0000000001"


def test_get_submissions_url_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_submissions`` hits ``data.sec.gov`` with the padded CIK."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(200, {"ok": True}), captured)
    client = SECClient(user_agent="Bot bot@example.com")
    payload = client.get_submissions("320193")
    assert payload == {"ok": True}
    assert (
        captured["url"]
        == "https://data.sec.gov/submissions/CIK0000320193.json"
    )


def test_get_company_facts_url_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_company_facts`` hits the xbrl companyfacts endpoint."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(200, {"facts": {}}), captured)
    client = SECClient(user_agent="Bot bot@example.com")
    client.get_company_facts("320193")
    assert (
        captured["url"]
        == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )


def test_get_company_concept_url_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_company_concept`` hits the companyconcept endpoint."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(200, {"units": {}}), captured)
    client = SECClient(user_agent="Bot bot@example.com")
    client.get_company_concept("320193", taxonomy="us-gaap", tag="Assets")
    assert (
        captured["url"]
        == "https://data.sec.gov/api/xbrl/companyconcept/"
        "CIK0000320193/us-gaap/Assets.json"
    )


def test_get_company_tickers_url_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_company_tickers`` downloads SEC's public ticker mapping."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(200, {"0": {}}), captured)
    client = SECClient(user_agent="Bot bot@example.com")
    payload = client.get_company_tickers()
    assert payload == {"0": {}}
    assert captured["url"] == "https://www.sec.gov/files/company_tickers.json"


def test_ticker_to_cik_returns_padded_cik(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ticker_to_cik`` resolves SEC ticker rows to 10-digit CIKs."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch,
        FakeResponse(
            200,
            {
                "0": {
                    "cik_str": 320193,
                    "ticker": "AAPL",
                    "title": "Apple Inc.",
                }
            },
        ),
        captured,
    )
    client = SECClient(user_agent="Bot bot@example.com")
    assert client.ticker_to_cik("aapl") == "0000320193"


def test_ticker_to_cik_raises_for_missing_ticker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing SEC ticker rows raise the same typed not-found error."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(200, {"0": {}}), captured)
    client = SECClient(user_agent="Bot bot@example.com")
    with pytest.raises(SECNotFoundError):
        client.ticker_to_cik("MISSING")


def test_get_filing_html_url_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_filing_html`` builds the Archives URL without accession dashes."""
    captured: dict[str, Any] = {}
    _patch_session_get(
        monkeypatch, FakeResponse(200, text="<html></html>"), captured
    )
    client = SECClient(user_agent="Bot bot@example.com")
    html = client.get_filing_html(
        accession_number="0000320193-21-000105",
        cik="320193",
        primary_doc="aapl-20210925.htm",
    )
    assert html == "<html></html>"
    assert (
        captured["url"]
        == "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019321000105/aapl-20210925.htm"
    )


def test_build_filing_document_url() -> None:
    """Archives document URL uses unpadded CIK and accession without dashes."""
    client = SECClient(user_agent="Bot bot@example.com")
    assert client.build_filing_document_url(
        cik="0000320193",
        accession_number="0000320193-21-000105",
        primary_document="aapl-20210925.htm",
    ) == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019321000105/aapl-20210925.htm"
    )


def test_404_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 404 response maps to :class:`SECNotFoundError`."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(404), captured)
    client = SECClient(user_agent="Bot bot@example.com")
    with pytest.raises(SECNotFoundError):
        client.get_submissions("0000320193")


def test_429_raises_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 429 response maps to :class:`SECRateLimitError`."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(429), captured)
    client = SECClient(user_agent="Bot bot@example.com")
    with pytest.raises(SECRateLimitError):
        client.get_company_facts("0000320193")


def test_500_raises_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 500 response maps to :class:`SECHTTPError`."""
    captured: dict[str, Any] = {}
    _patch_session_get(monkeypatch, FakeResponse(500), captured)
    client = SECClient(user_agent="Bot bot@example.com")
    with pytest.raises(SECHTTPError):
        client.get_submissions("0000320193")


def test_all_custom_errors_inherit_from_base() -> None:
    """All SECClientError subclasses should be catchable via the base type."""
    assert issubclass(SECNotFoundError, SECClientError)
    assert issubclass(SECRateLimitError, SECClientError)
    assert issubclass(SECHTTPError, SECClientError)


def test_wait_for_slot_sleeps_to_meet_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_wait_for_slot`` must sleep enough to honor the configured rate."""
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("src.data.sec_client.time.sleep", fake_sleep)
    # Each ``_wait_for_slot`` reads ``time.monotonic`` twice (probe + record).
    # Provide enough monotonic values for three slot waits.
    monotonic_seq: list[float] = [
        0.0, 0.0,            # call 1: no prior, set to 0.0
        0.05, 0.05,          # call 2: probe 0.05, sleep to 0.5, record 0.5
        0.6, 0.6,            # call 3: probe 0.6, already past 0.5 -> no sleep
    ]
    counter = {"n": 0}

    def fake_monotonic() -> float:
        idx = min(counter["n"], len(monotonic_seq) - 1)
        counter["n"] += 1
        return monotonic_seq[idx]

    monkeypatch.setattr("src.data.sec_client.time.monotonic", fake_monotonic)

    client = SECClient(
        user_agent="Bot bot@example.com", rate_limit_per_second=2.0
    )
    client._wait_for_slot()
    client._wait_for_slot()
    client._wait_for_slot()
    # First call: no prior timestamp, no sleep.
    # Second call: probe=0.05, must reach 0.5s -> sleep 0.45.
    # Third call: probe=0.6, already past 0.5s -> no sleep.
    assert pytest.approx(sleeps[0], rel=1e-9) == 0.45
    assert len(sleeps) == 1


def test_wait_for_slot_zero_rate_does_not_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rate limit of zero (or negative) should not sleep at all."""
    sleeps: list[float] = []

    monkeypatch.setattr("src.data.sec_client.time.sleep", sleeps.append)
    monkeypatch.setattr(
        "src.data.sec_client.time.monotonic", lambda: 0.0
    )
    client = SECClient(
        user_agent="Bot bot@example.com", rate_limit_per_second=0.0
    )
    client._wait_for_slot()
    assert sleeps == []


def test_request_uses_real_time_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_request`` should call ``time.sleep`` indirectly via the slot wait."""
    _patch_session_get(monkeypatch, FakeResponse(200, {}), {})
    sleeps: list[float] = []
    monkeypatch.setattr("src.data.sec_client.time.sleep", sleeps.append)
    # Tenacity plus our own probes consume several monotonic calls; provide
    # values that make the slot gap large enough to skip sleeping.
    counter = {"n": 0}
    values: list[float] = []

    def fake_monotonic() -> float:
        if counter["n"] < len(values):
            counter["n"] += 1
            return values[counter["n"] - 1]
        counter["n"] += 1
        return 100.0

    monkeypatch.setattr("src.data.sec_client.time.monotonic", fake_monotonic)
    client = SECClient(
        user_agent="Bot bot@example.com", rate_limit_per_second=10.0
    )
    client.get_submissions("0000320193")
    # No real-time sleep required because the gap was 100 seconds.
    assert sleeps == []


def test_session_attribute_is_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``session`` property returns the underlying ``requests.Session``."""
    _patch_session_get(monkeypatch, FakeResponse(200, {}), {})
    client = SECClient(user_agent="Bot bot@example.com")
    from requests import Session

    assert isinstance(client.session, Session)


def test_wait_for_slot_actually_uses_time_module() -> None:
    """Sanity check: importing the module makes ``time.sleep`` reachable."""
    import src.data.sec_client as module

    assert hasattr(module, "time")
    assert hasattr(module.time, "sleep")
    assert module.time.sleep is time.sleep
