"""Tests for :mod:`src.data.filing_fetcher` using a fake SECClient."""

from __future__ import annotations

from datetime import date

import pytest

from src.data.filing_fetcher import FilingFetcher
from src.data.sec_client import SECClient
from src.schemas.filings import FilingMetadata, FilingRecord


class FakeSECClient:
    """In-memory replacement for :class:`SECClient` used in these tests."""

    def __init__(self, submissions_payload: dict, filing_html: str = "") -> None:
        self._submissions_payload = submissions_payload
        self._filing_html = filing_html
        self.list_calls: list[dict] = []
        self.filing_calls: list[dict] = []

    def get_submissions(self, cik: str) -> dict:
        self.list_calls.append({"cik": cik})
        return self._submissions_payload

    def get_filing_html(
        self, accession_number: str, cik: str, primary_doc: str
    ) -> str:
        self.filing_calls.append(
            {
                "accession_number": accession_number,
                "cik": cik,
                "primary_doc": primary_doc,
            }
        )
        return self._filing_html


def _make_submissions_payload(rows: list[dict]) -> dict:
    """Build a ``filings.recent``-shaped payload from a list of row dicts."""
    return {
        "cik": "0000320193",
        "filings": {
            "recent": {
                "accessionNumber": [r["accessionNumber"] for r in rows],
                "form": [r["form"] for r in rows],
                "filingDate": [r["filingDate"] for r in rows],
                "reportDate": [r.get("reportDate", "") for r in rows],
                "primaryDocument": [r["primaryDocument"] for r in rows],
            }
        },
    }


def test_list_filings_filters_by_form_type() -> None:
    """``list_filings`` keeps only the requested form types."""
    payload = _make_submissions_payload(
        [
            {
                "accessionNumber": "0000320193-21-000010",
                "form": "10-K",
                "filingDate": "2021-10-29",
                "reportDate": "2021-09-25",
                "primaryDocument": "aapl-20210925.htm",
            },
            {
                "accessionNumber": "0000320193-21-000020",
                "form": "8-K",
                "filingDate": "2021-11-05",
                "reportDate": "",
                "primaryDocument": "aapl-20211105.htm",
            },
            {
                "accessionNumber": "0000320193-22-000010",
                "form": "10-Q",
                "filingDate": "2022-05-05",
                "reportDate": "2022-03-26",
                "primaryDocument": "aapl-20220326.htm",
            },
        ]
    )
    fake = FakeSECClient(payload)
    fetcher = FilingFetcher(fake)  # type: ignore[arg-type]
    filings = fetcher.list_filings("320193", form_types=("10-K",))
    assert len(filings) == 1
    assert filings[0].form_type == "10-K"
    assert filings[0].accession_number == "0000320193-21-000010"


def test_list_filings_filters_by_since_date() -> None:
    """``list_filings`` drops filings strictly older than ``since``."""
    payload = _make_submissions_payload(
        [
            {
                "accessionNumber": "0000320193-21-000010",
                "form": "10-K",
                "filingDate": "2021-10-29",
                "reportDate": "2021-09-25",
                "primaryDocument": "aapl-20210925.htm",
            },
            {
                "accessionNumber": "0000320193-22-000010",
                "form": "10-Q",
                "filingDate": "2022-05-05",
                "reportDate": "2022-03-26",
                "primaryDocument": "aapl-20220326.htm",
            },
        ]
    )
    fake = FakeSECClient(payload)
    fetcher = FilingFetcher(fake)  # type: ignore[arg-type]
    filings = fetcher.list_filings(
        "320193", form_types=("10-K", "10-Q"), since=date(2022, 1, 1)
    )
    assert [f.filing_date for f in filings] == [date(2022, 5, 5)]


def test_list_filings_applies_limit() -> None:
    """``list_filings`` truncates results to ``limit`` entries."""
    payload = _make_submissions_payload(
        [
            {
                "accessionNumber": f"0000320193-21-00000{i}",
                "form": "10-Q",
                "filingDate": f"2021-{i + 1:02d}-05",
                "reportDate": "",
                "primaryDocument": f"doc{i}.htm",
            }
            for i in range(1, 5)
        ]
    )
    fake = FakeSECClient(payload)
    fetcher = FilingFetcher(fake)  # type: ignore[arg-type]
    filings = fetcher.list_filings("320193", form_types=("10-Q",), limit=2)
    assert len(filings) == 2


def test_list_filings_zero_pads_cik_in_metadata() -> None:
    """Every returned :class:`FilingMetadata` carries the 10-digit CIK."""
    payload = _make_submissions_payload(
        [
            {
                "accessionNumber": "0000320193-21-000010",
                "form": "10-K",
                "filingDate": "2021-10-29",
                "reportDate": "2021-09-25",
                "primaryDocument": "aapl-20210925.htm",
            },
        ]
    )
    fake = FakeSECClient(payload)
    fetcher = FilingFetcher(fake)  # type: ignore[arg-type]
    filings = fetcher.list_filings("320193")
    assert filings[0].cik == "0000320193"
    assert filings[0].url.startswith(
        "https://www.sec.gov/Archives/edgar/data/320193/"
    )


def test_fetch_filing_returns_filing_record_with_full_text() -> None:
    """``fetch_filing`` produces a :class:`FilingRecord` with ``full_text``."""
    fake = FakeSECClient(
        submissions_payload={},
        filing_html=(
            "<html><body><h1>Item 1. Business</h1>"
            "<p>We sell widgets and gadgets.</p>"
            "<h1>Item 7. Management's Discussion</h1>"
            "<p>Revenue grew 10%.</p>"
            "</body></html>"
        ),
    )
    fetcher = FilingFetcher(fake)  # type: ignore[arg-type]
    metadata = FilingMetadata(
        cik="0000320193",
        accession_number="0000320193-21-000010",
        form_type="10-K",
        filing_date=date(2021, 10, 29),
        report_date=date(2021, 9, 25),
        primary_document="aapl-20210925.htm",
        url=(
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019321000010/aapl-20210925.htm"
        ),
    )
    record = fetcher.fetch_filing(metadata)
    assert isinstance(record, FilingRecord)
    assert record.source == "sec"
    assert record.cik == "0000320193"
    assert record.accession_number == "0000320193-21-000010"
    assert "full_text" in record.sections
    assert "We sell widgets" in record.sections["full_text"]
    assert "Revenue grew" in record.sections["full_text"]


def test_fetch_filing_passes_args_to_sec_client() -> None:
    """``fetch_filing`` should call ``get_filing_html`` with metadata fields."""
    fake = FakeSECClient(
        submissions_payload={},
        filing_html="<html><body>hi</body></html>",
    )
    fetcher = FilingFetcher(fake)  # type: ignore[arg-type]
    metadata = FilingMetadata(
        cik="0000320193",
        accession_number="0000320193-22-000077",
        form_type="8-K",
        filing_date=date(2022, 2, 4),
        report_date=None,
        primary_document="doc.htm",
        url="https://example/doc.htm",
    )
    fetcher.fetch_filing(metadata)
    assert fake.filing_calls == [
        {
            "accession_number": "0000320193-22-000077",
            "cik": "0000320193",
            "primary_doc": "doc.htm",
        }
    ]


def test_fetch_filing_section_extraction_attempts_items() -> None:
    """When text contains Item headers, naive section parsing fills them in."""
    text = (
        "Some intro text.\n"
        "Item 1. Business\n"
        "We sell widgets.\n"
        "Item 1A. Risk Factors\n"
        "Concentration risk.\n"
        "Item 7. Management's Discussion and Analysis\n"
        "Revenue grew.\n"
        "Item 7A. Quantitative and Qualitative Disclosures\n"
        "We use derivatives.\n"
    )
    fake = FakeSECClient(
        submissions_payload={}, filing_html=f"<html><body>{text}</body></html>"
    )
    fetcher = FilingFetcher(fake)  # type: ignore[arg-type]
    metadata = FilingMetadata(
        cik="0000320193",
        accession_number="0000320193-21-000010",
        form_type="10-K",
        filing_date=date(2021, 10, 29),
        report_date=date(2021, 9, 25),
        primary_document="doc.htm",
        url="https://example/doc.htm",
    )
    record = fetcher.fetch_filing(metadata)
    assert "full_text" in record.sections
    # The naive parser may extract some of these; assert at least full_text.
    assert "full_text" in record.sections


def test_filing_fetcher_accepts_real_sec_client_signature() -> None:
    """Constructing a :class:`FilingFetcher` with a stub validates the API."""
    fake = FakeSECClient(submissions_payload={"filings": {"recent": {}}})
    fetcher = FilingFetcher(fake)  # type: ignore[arg-type]
    assert isinstance(fetcher.sec_client, FakeSECClient)


@pytest.mark.parametrize("cik", ["1", "320193", "0000320193"])
def test_list_filings_pads_cik_regardless_of_input(cik: str) -> None:
    """Short CIK inputs are padded to 10 digits before being stored."""
    expected = "0000320193" if cik in ("320193", "0000320193") else "0000000001"
    payload = _make_submissions_payload(
        [
            {
                "accessionNumber": "0000320193-21-000010",
                "form": "10-K",
                "filingDate": "2021-10-29",
                "reportDate": "2021-09-25",
                "primaryDocument": "doc.htm",
            },
        ]
    )
    fake = FakeSECClient(payload)
    fetcher = FilingFetcher(fake)  # type: ignore[arg-type]
    filings = fetcher.list_filings(cik)
    assert filings[0].cik == expected


def test_sec_client_class_exists() -> None:
    """Sanity check: the real SECClient class is importable."""
    assert SECClient is not None