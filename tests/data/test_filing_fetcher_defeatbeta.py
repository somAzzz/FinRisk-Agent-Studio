"""Tests for :func:`fetch_filings_catalog_defeatbeta`.

Defeatbeta returns a ``pandas.DataFrame`` for ``ticker.sec_filing()``.
We stub that with a ``FakeDataFrame`` and patch the ``Ticker`` factory in
``src.data.providers.defeatbeta`` to return canned data without hitting
HuggingFace.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.data.providers.defeatbeta import (
    fetch_filings_catalog_defeatbeta,
)


class FakeDataFrame:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.empty = len(rows) == 0

    def to_dict(self, _orient: str = "records") -> list[dict[str, Any]]:
        return list(self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)


class FakeTicker:
    def __init__(self, sec_rows: list[dict[str, Any]]) -> None:
        self._sec_rows = sec_rows

    def sec_filing(self) -> FakeDataFrame:
        return FakeDataFrame(self._sec_rows)


def _install_fake_ticker(monkeypatch: pytest.MonkeyPatch, sec_rows: list[dict[str, Any]]) -> None:
    def factory(symbol: str, **_kwargs: Any) -> FakeTicker:
        return FakeTicker(sec_rows)

    import src.data.providers.defeatbeta as mod

    monkeypatch.setattr(mod, "_TICKER_CLS", factory)
    monkeypatch.setattr(mod, "_DEFEATBETA_IMPORT_ERROR", None)


def _sample_filings() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "AAPL",
            "cik": "0000320193",
            "accession_number": "0000320193-24-000081",
            "company_name": "Apple Inc.",
            "form_type": "10-Q",
            "form_type_description": "Quarterly Report",
            "filing_date": "2024-05-02",
            "report_date": "2024-03-30",
            "acceptance_date_time": "2024-05-02T05:00:00.000Z",
            "filing_url": ("https://www.sec.gov/Archives/edgar/data/320193/000032019324000081"),
        },
        {
            "symbol": "AAPL",
            "cik": "0000320193",
            "accession_number": "0000320193-23-000106",
            "company_name": "Apple Inc.",
            "form_type": "10-K",
            "form_type_description": "Annual Report",
            "filing_date": "2023-10-27",
            "report_date": "2023-09-30",
            "acceptance_date_time": "2023-10-27T05:00:00.000Z",
            "filing_url": ("https://www.sec.gov/Archives/edgar/data/320193/000032019323000106"),
        },
        {
            "symbol": "AAPL",
            "cik": "0000320193",
            "accession_number": "0000320193-24-000002",
            "company_name": "Apple Inc.",
            "form_type": "8-K",
            "form_type_description": "Current Report",
            "filing_date": "2024-01-30",
            "report_date": "2024-01-30",
            "acceptance_date_time": "2024-01-30T05:00:00.000Z",
            "filing_url": ("https://www.sec.gov/Archives/edgar/data/320193/000032019324000002"),
        },
    ]


def test_catalog_returns_filings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each row becomes a :class:`FilingMetadata` with mapped fields."""
    _install_fake_ticker(monkeypatch, _sample_filings())
    metas = fetch_filings_catalog_defeatbeta("aapl")
    assert len(metas) == 3
    assert metas[0].cik == "0000320193"
    assert metas[0].accession_number == "0000320193-24-000081"
    assert metas[0].form_type == "10-Q"
    assert metas[0].filing_date.year == 2024
    assert metas[0].report_date is not None and metas[0].report_date.year == 2024
    assert metas[0].url.startswith("https://www.sec.gov/Archives/edgar/data/320193/")


def test_catalog_filters_by_form_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """``form_types`` filters out unwanted filing types."""
    _install_fake_ticker(monkeypatch, _sample_filings())
    metas = fetch_filings_catalog_defeatbeta("AAPL", form_types=["10-K", "10-Q"])
    forms = [m.form_type for m in metas]
    assert "8-K" not in forms
    assert set(forms) == {"10-K", "10-Q"}


def test_catalog_filters_by_since(monkeypatch: pytest.MonkeyPatch) -> None:
    """``since`` drops filings filed before the cutoff."""
    from datetime import date

    _install_fake_ticker(monkeypatch, _sample_filings())
    metas = fetch_filings_catalog_defeatbeta("AAPL", form_types=["10-K", "10-Q"], since=date(2024, 1, 1))
    assert all(m.filing_date.year >= 2024 for m in metas)


def test_catalog_respects_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """``limit`` caps the number of returned records."""
    _install_fake_ticker(monkeypatch, _sample_filings())
    metas = fetch_filings_catalog_defeatbeta("AAPL", limit=2)
    assert len(metas) == 2


def test_catalog_empty_when_optional_dep_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If defeatbeta-api is not importable, return ``[]``."""
    import src.data.providers.defeatbeta as mod
    from src.data.transcripts import TranscriptProviderConfigError

    monkeypatch.setattr(mod, "_TICKER_CLS", None)
    monkeypatch.setattr(mod, "_DEFEATBETA_IMPORT_ERROR", ImportError("not installed"))

    def raise_config(*_a: Any, **_kw: Any) -> Any:
        raise TranscriptProviderConfigError("defeatbeta-api not available")

    monkeypatch.setattr(mod, "_ensure_defeatbeta", raise_config)
    assert fetch_filings_catalog_defeatbeta("AAPL") == []


def test_catalog_handles_empty_dataframe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty defeatbeta output returns ``[]``."""
    _install_fake_ticker(monkeypatch, [])
    assert fetch_filings_catalog_defeatbeta("AAPL") == []
