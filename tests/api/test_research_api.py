from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from src.api.research import (
    FinancialResearchService,
    calculate_valuation_scenarios,
    get_financial_snapshot,
    set_financial_research_service_for_tests,
)
from src.research.valuation import ScenarioValuationRequest


@dataclass
class _Identity:
    ticker: str = "AAPL"
    cik: str = "0000320193"
    name: str = "Apple Inc."


class _Resolver:
    def resolve(self, ticker: str):
        return None if ticker == "MISS" else _Identity(ticker=ticker.upper())


def _facts(_cik: str) -> dict:
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 100,
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "fy": 2023,
                                "fp": "FY",
                                "accn": "annual",
                            }
                        ]
                    }
                }
            }
        }
    }


@pytest.fixture(autouse=True)
def _service():
    set_financial_research_service_for_tests(
        FinancialResearchService(
            ticker_resolver=_Resolver(),
            company_facts_fetcher=_facts,
        )
    )
    yield
    set_financial_research_service_for_tests(FinancialResearchService())


@pytest.mark.asyncio
async def test_financial_snapshot_endpoint_returns_typed_history() -> None:
    snapshot = await get_financial_snapshot("aapl", date(2024, 12, 31))

    assert snapshot.ticker == "AAPL"
    assert snapshot.as_of.date() == date(2024, 12, 31)
    assert snapshot.series("revenue", "annual")[0].value == 100


@pytest.mark.asyncio
async def test_financial_snapshot_endpoint_maps_missing_ticker_to_404() -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as raised:
        await get_financial_snapshot("MISS", None)
    assert raised.value.status_code == 404


@pytest.mark.asyncio
async def test_valuation_endpoint_uses_only_explicit_request_assumptions() -> None:
    request = ScenarioValuationRequest.model_validate(
        {
            "ticker": "ACME",
            "base_revenue": 1000,
            "net_debt": 0,
            "diluted_shares": 100,
            "forecast_years": 1,
            "scenarios": [
                {
                    "name": "bear", "annual_revenue_growth": 0,
                    "terminal_operating_margin": 0.1,
                    "ev_to_operating_income_multiple": 10,
                },
                {
                    "name": "base", "annual_revenue_growth": 0.1,
                    "terminal_operating_margin": 0.2,
                    "ev_to_operating_income_multiple": 12,
                },
                {
                    "name": "bull", "annual_revenue_growth": 0.2,
                    "terminal_operating_margin": 0.3,
                    "ev_to_operating_income_multiple": 15,
                },
            ],
        }
    )
    response = await calculate_valuation_scenarios(request)
    assert response.scenarios[1].assumptions.annual_revenue_growth == 0.1
