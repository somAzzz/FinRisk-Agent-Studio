from datetime import UTC, date, datetime
from types import SimpleNamespace

from src.schemas.filings import FilingMetadata, FilingRecord
from src.schemas.transcripts import Transcript, TranscriptTurn
from src.tools.catalog import build_project_tool_catalog


class FakeResolver:
    def resolve(self, ticker: str):
        if ticker.upper() == "MISS":
            return None
        return SimpleNamespace(
            ticker=ticker.upper(),
            cik="0000320193",
            name="Apple Inc.",
        )


class FakeFilingFetcher:
    def __init__(self) -> None:
        self.list_calls: list[dict] = []
        self.fetch_calls: list[FilingMetadata] = []
        self.metadata = FilingMetadata(
            cik="0000320193",
            accession_number="0000320193-24-000001",
            form_type="10-K",
            filing_date=date(2024, 10, 31),
            report_date=date(2024, 9, 28),
            primary_document="aapl-20240928.htm",
            url="https://sec.example/aapl-10k",
        )

    def list_filings(self, cik, form_types=("10-K",), since=None, limit=None):
        self.list_calls.append(
            {
                "cik": cik,
                "form_types": form_types,
                "since": since,
                "limit": limit,
            }
        )
        return [self.metadata]

    def fetch_filing(self, metadata: FilingMetadata) -> FilingRecord:
        self.fetch_calls.append(metadata)
        return FilingRecord(
            source="sec",
            cik=metadata.cik,
            form_type=metadata.form_type,
            filing_date=metadata.filing_date,
            accession_number=metadata.accession_number,
            sections={
                "full_text": "Full filing text",
                "section_1a": "Risk factors text",
            },
            url=metadata.url,
            metadata={"primary_document": metadata.primary_document},
        )


class FakeTranscriptProvider:
    provider_name = "fake_transcripts"

    def get_transcript(self, ticker: str, year: int, quarter: int) -> Transcript:
        return Transcript(
            ticker=ticker,
            company_name="Apple Inc.",
            year=year,
            quarter=quarter,
            provider=self.provider_name,
            transcript_id=f"{ticker}-{year}Q{quarter}",
            title="Apple earnings call",
            published_at=datetime(2025, 1, 31, tzinfo=UTC),
            url="https://example.com/transcript",
            turns=[
                TranscriptTurn(
                    speaker="CEO",
                    role="ceo",
                    text="Prepared remarks",
                    section="prepared_remarks",
                    turn_index=0,
                ),
                TranscriptTurn(
                    speaker="Analyst",
                    role="analyst",
                    text="Supply chain question",
                    section="qa",
                    turn_index=1,
                ),
            ],
        )


def fake_metrics_fetcher(ticker: str) -> dict[str, float | None]:
    return {"ttm_pe": 25.0, "roe": 0.52, "debt_to_equity": None}


def fake_company_facts_fetcher(_cik: str) -> dict:
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 391035000000,
                                "end": "2024-09-28",
                                "form": "10-K",
                                "accn": "0000320193-24-000001",
                            }
                        ]
                    }
                }
            }
        }
    }


def _company_catalog():
    return build_project_tool_catalog(
        ticker_resolver=FakeResolver(),
        filing_fetcher=FakeFilingFetcher(),
        transcript_provider=FakeTranscriptProvider(),
        metrics_fetcher=fake_metrics_fetcher,
        company_facts_fetcher=fake_company_facts_fetcher,
        scope="company_research",
    )


def test_default_catalog_keeps_data_tools_out() -> None:
    catalog = build_project_tool_catalog(
        ticker_resolver=FakeResolver(),
        filing_fetcher=FakeFilingFetcher(),
    )

    assert catalog.names == ["web_search", "web_fetch", "search_and_fetch"]


def test_company_research_scope_includes_data_tools() -> None:
    catalog = _company_catalog()

    assert "sec_list_filings" in catalog.names
    assert "sec_fetch_filing" in catalog.names
    assert "transcript_lookup" in catalog.names
    assert "financial_metrics_lookup" in catalog.names
    assert "xbrl_fact_lookup" in catalog.names


def test_sec_list_filings_tool_uses_resolver_and_fetcher() -> None:
    fetcher = FakeFilingFetcher()
    catalog = build_project_tool_catalog(
        ticker_resolver=FakeResolver(),
        filing_fetcher=fetcher,
        scope="finrisk_filing",
    )

    result = catalog.tool_map["sec_list_filings"](
        ticker="AAPL",
        form_types=["10-K"],
        since="2024-01-01",
        limit=99,
    )

    assert result["tool"] == "sec_list_filings"
    assert result["evidence_kind"] == "filing"
    assert fetcher.list_calls[0]["cik"] == "0000320193"
    assert fetcher.list_calls[0]["limit"] == 20
    assert result["data"]["filings"][0]["accession_number"] == "0000320193-24-000001"


def test_sec_fetch_filing_tool_returns_requested_section() -> None:
    fetcher = FakeFilingFetcher()
    catalog = build_project_tool_catalog(
        ticker_resolver=FakeResolver(),
        filing_fetcher=fetcher,
        scope="finrisk_filing",
    )

    result = catalog.tool_map["sec_fetch_filing"](
        ticker="AAPL",
        accession_number="0000320193-24-000001",
        section="1A",
    )

    assert fetcher.fetch_calls[0].accession_number == "0000320193-24-000001"
    assert result["data"]["section"] == "section_1a"
    assert result["data"]["text"] == "Risk factors text"


def test_transcript_lookup_tool_filters_section() -> None:
    catalog = _company_catalog()

    result = catalog.tool_map["transcript_lookup"](
        ticker="AAPL",
        year=2025,
        quarter=1,
        section="qa",
    )

    assert result["evidence_kind"] == "transcript"
    assert result["data"]["provider"] == "fake_transcripts"
    assert len(result["data"]["turns"]) == 1
    assert result["data"]["turns"][0]["section"] == "qa"


def test_financial_metrics_lookup_tool_filters_metrics() -> None:
    catalog = _company_catalog()

    result = catalog.tool_map["financial_metrics_lookup"](
        ticker="AAPL",
        metrics=["roe"],
    )

    assert result["evidence_kind"] == "financial_metric"
    assert result["data"]["metrics"] == {"roe": 0.52}


def test_xbrl_fact_lookup_tool_extracts_concepts() -> None:
    catalog = _company_catalog()

    result = catalog.tool_map["xbrl_fact_lookup"](
        ticker="AAPL",
        concepts=["Revenues"],
    )

    assert result["data"]["facts"][0]["concept"] == "Revenues"
    assert result["data"]["facts"][0]["value"] == 391035000000.0


def test_sec_tools_return_explainable_error_when_ticker_missing() -> None:
    catalog = build_project_tool_catalog(
        ticker_resolver=FakeResolver(),
        filing_fetcher=FakeFilingFetcher(),
        scope="finrisk_filing",
    )

    result = catalog.tool_map["sec_list_filings"](ticker="MISS")

    assert result["data"]["filings"] == []
    assert result["data"]["error"] == "ticker not resolved"
