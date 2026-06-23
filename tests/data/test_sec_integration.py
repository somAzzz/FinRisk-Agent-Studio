"""Optional SEC live-data integration tests.

These tests are skipped by default. Enable them with::

    RUN_SEC_INTEGRATION=1 uv run pytest tests/data/test_sec_integration.py -m integration

They hit the real SEC submissions endpoint and download primary filing
documents. Use sparingly to avoid rate limiting.
"""

from __future__ import annotations

import os

import pytest

from src.data.filing_fetcher import FilingFetcher
from src.data.sec_client import SECClient
from src.data.sec_sections import SectionParser
from src.data.ticker_resolver import TickerResolver
from src.schemas.filings import FilingMetadata


pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.environ.get("RUN_SEC_INTEGRATION") == "1"


pytestmark_skip = pytest.mark.skipif(
    not _integration_enabled(),
    reason="set RUN_SEC_INTEGRATION=1 to enable",
)


@pytestmark_skip
def test_ticker_resolver_resolves_apple_to_apple_cik() -> None:
    """``AAPL`` resolves to ``0000320193`` via the SEC company tickers JSON."""
    ident = TickerResolver().resolve("AAPL")
    assert ident is not None
    assert ident.ticker == "AAPL"
    assert ident.cik == "0000320193"
    assert ident.source in {"sec", "cache", "fallback"}


@pytestmark_skip
def test_sec_submissions_returns_recent_filings() -> None:
    """Apple's SEC submissions list is non-empty and contains a 10-K."""
    client = SECClient()
    payload = client.get_submissions("0000320193")
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    assert len(forms) > 0
    assert "10-K" in forms


@pytestmark_skip
def test_filing_fetcher_downloads_recent_apple_10q() -> None:
    """At least one Apple 10-Q can be downloaded and has expected sections."""
    client = SECClient()
    payload = client.get_submissions("0000320193")
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])

    target_idx: int | None = None
    for idx, form in enumerate(forms[:50]):
        if form == "10-Q":
            target_idx = idx
            break
    assert target_idx is not None, "no 10-Q in first 50 submissions"

    from datetime import date

    metadata = FilingMetadata(
        cik="0000320193",
        accession_number=accession_numbers[target_idx],
        form_type="10-Q",
        filing_date=date.fromisoformat(filing_dates[target_idx]),
        report_date=None,
        primary_document=primary_docs[target_idx],
        url=(
            "https://www.sec.gov/Archives/edgar/data/320193/"
            f"{accession_numbers[target_idx].replace('-', '')}/"
            f"{primary_docs[target_idx]}"
        ),
    )
    fetcher = FilingFetcher(client, section_parser=SectionParser())
    record = fetcher.fetch_filing(metadata)
    assert record.cik == "0000320193"
    assert record.form_type == "10-Q"
    # Production parser should at least return full_text and some sections.
    assert "full_text" in record.sections
    assert len(record.sections) >= 2
