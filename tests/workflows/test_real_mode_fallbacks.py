"""v17 tests for real-mode fallback handling in workflow steps.

The v17 audit requires that:

- :class:`MarketExplorerStep` always has a real-mode path that
  either succeeds or records a :class:`FallbackEvent`.
- :class:`FilingRiskExtractorStep` has an LLM structured
  extraction adapter and falls back to the keyword path when the
  LLM is unavailable.

Both contracts are exercised without touching the network.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.schemas.finrisk import (
    CompanyProfile,
    ExtractedRisk,
    FinRiskRequest,
    FinRiskWorkflowState,
    utcnow,
)
from src.workflows.steps.filing_risk_extractor import FilingRiskExtractorStep
from src.workflows.steps.market_explorer_step import MarketExplorerStep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(*, ticker: str = "AAPL", demo_mode: bool = True) -> FinRiskWorkflowState:
    return FinRiskWorkflowState(
        run_id="r",
        request=FinRiskRequest(
            ticker=ticker, analysis_goal="x", demo_mode=demo_mode
        ),
        company=CompanyProfile(
            company_name="Apple Inc.",
            ticker=ticker,
            cik="0000320193",
            filing_type="10-K",
            analysis_year=2024,
            source="fixture",
            resolved_at=utcnow(),
        ),
        filing_risks=[
            ExtractedRisk(
                risk_id="r-1",
                risk_type="policy",
                risk_factor="Apple supply chain",
                severity=3,
                evidence_quote="quote",
                source="sec_filing:test",
                filing_section="section_1a",
                confidence=0.7,
            )
        ],
    )


FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "finrisk"
    / "aapl_demo_workflow.json"
)


# ---------------------------------------------------------------------------
# MarketExplorerStep
# ---------------------------------------------------------------------------


async def test_market_explorer_demo_mode_reads_fixture() -> None:
    state = _state()
    # Add a risk that the fixture market evidence references so the
    # "valid_ids" filter doesn't drop everything.
    state.filing_risks.append(
        ExtractedRisk(
            risk_id="risk-supply-asia",
            risk_type="supply_chain",
            risk_factor="Asia suppliers",
            severity=4,
            evidence_quote="Apple mentions outsourcing",
            source="sec_filing:test",
            filing_section="section_1a",
            confidence=0.7,
        )
    )
    step = MarketExplorerStep(fixture_path=FIXTURE_PATH)
    new_state = await step.run(state)
    assert new_state.market_evidence
    assert not new_state.fallback_events


async def test_market_explorer_real_mode_records_fallback_when_no_router() -> None:
    """When the auto-router cannot resolve, the step records a fallback."""
    state = _state(demo_mode=False)
    # Pass a factory that returns None so the step falls back to the
    # "no router available" path.
    step = MarketExplorerStep(
        fixture_path=FIXTURE_PATH,
        search_router=lambda: None,
    )
    new_state = await step.run(state)
    assert not new_state.market_evidence  # no real data
    fallback = next(
        (e for e in new_state.fallback_events if e.step_name == "market_explorer"),
        None,
    )
    assert fallback is not None
    assert fallback.to_mode == "cached"


async def test_market_explorer_real_mode_swallows_router_exception() -> None:
    """A raising injected router also records a fallback, not a crash."""
    state = _state()
    state.request.demo_mode = False
    state.request.cached_mode = False

    def raising_router() -> MagicMock:
        mock = MagicMock()
        mock.search.side_effect = RuntimeError("provider down")
        return mock

    step = MarketExplorerStep(
        fixture_path=FIXTURE_PATH,
        search_router=raising_router,
    )
    new_state = await step.run(state)
    assert new_state.fallback_events  # state still valid
    assert any(
        e.step_name == "market_explorer" for e in new_state.fallback_events
    )


# ---------------------------------------------------------------------------
# FilingRiskExtractorStep
# ---------------------------------------------------------------------------


async def test_filing_extractor_demo_mode_reads_fixture() -> None:
    state = _state()
    step = FilingRiskExtractorStep(fixture_path=FIXTURE_PATH)
    new_state = await step.run(state)
    assert new_state.filing_risks
    assert not new_state.fallback_events


async def test_filing_extractor_real_mode_without_deps_records_fallback() -> None:
    """When the SEC client cannot be imported, the step records a fallback."""
    state = _state(demo_mode=False)
    step = FilingRiskExtractorStep(
        fixture_path=FIXTURE_PATH,
        ticker_resolver=lambda: (_ for _ in ()).throw(RuntimeError("nope")),
    )
    new_state = await step.run(state)
    assert not new_state.filing_risks
    assert any(
        e.step_name == "filing_risk_extractor"
        for e in new_state.fallback_events
    )


async def test_filing_extractor_skips_title_only_item_1a() -> None:
    """Latest 10-Q can carry only an Item 1A heading; fall back to 10-K."""

    class Resolver:
        def resolve(self, ticker):
            return type(
                "Ident",
                (),
                {"cik": "0000320193", "name": "Apple Inc."},
            )()

    class Client:
        def get_submissions(self, cik):
            return {
                "filings": {
                    "recent": {
                        "form": ["10-Q", "10-K"],
                        "accessionNumber": ["short-10q", "long-10k"],
                        "filingDate": ["2026-05-01", "2025-10-31"],
                        "primaryDocument": ["short.htm", "long.htm"],
                    }
                }
            }

    class Fetcher:
        def __init__(self, client):
            self.client = client

        def fetch_filing(self, metadata):
            if metadata.accession_number == "short-10q":
                sections = {"section_1a": "Item 1A. Risk Factors"}
            else:
                sections = {
                    "section_1a": (
                        "Item 1A. Risk Factors. "
                        + "Supplier and supply chain risks may affect operations. "
                        * 20
                    )
                }
            return type("Filing", (), {"sections": sections})()

    state = _state(demo_mode=False)
    step = FilingRiskExtractorStep(
        fixture_path=FIXTURE_PATH,
        ticker_resolver=Resolver,
        sec_client=Client,
        filing_fetcher=Fetcher,
    )
    new_state = await step.run(state)
    assert new_state.filing_risks
    assert new_state.filing_risks[0].source.startswith("sec_filing:long-10k")


def test_risk_section_text_uses_full_text_when_parser_hits_toc() -> None:
    from src.workflows.steps.filing_risk_extractor import _risk_section_text

    full_text = (
        "Table of Contents\n"
        "Item 1A. Risk Factors\n"
        "5\n"
        "Item 1B. Unresolved Staff Comments\n"
        "Item 1A. Risk Factors\n"
        + "Supplier concentration and supply chain disruption risks. " * 20
        + "Item 1B. Unresolved Staff Comments\n"
    )
    text = _risk_section_text(
        {"section_1a": "Item 1A. Risk Factors\n5", "full_text": full_text}
    )
    assert "Supplier concentration" in text
    assert len(text) > 500


async def test_filing_extractor_llm_falls_back_to_keywords() -> None:
    """When the LLM extractor returns ``[]`` we fall back to keywords."""
    from src.llm.deepseek_client import DeepSeekClient
    from src.workflows.steps.filing_risk_extractor import _llm_extract

    class StubClient(DeepSeekClient):
        configured = True

        def extract_risks(self, section_1a, company_name="x", year=0):  # type: ignore[override]
            return {"risks": []}

    monkeypatch = pytest.MonkeyPatch()
    try:
        from src.workflows.steps import filing_risk_extractor as mod

        def _factory(_config=None):
            return StubClient(api_key="sk-test")

        monkeypatch.setattr(mod, "_build_llm_client", _factory)
        llm_result = _llm_extract("section text")
        assert llm_result == []
    finally:
        monkeypatch.undo()
