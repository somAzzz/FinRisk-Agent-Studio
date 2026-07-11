from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.research.valuation import (
    DiscountedCashFlowRequest,
    MultipleValuationRequest,
    ScenarioValuationRequest,
    SensitivityMatrixRequest,
    ValuationScenarioInput,
    calculate_discounted_cash_flow,
    calculate_multiple_valuation,
    calculate_scenario_valuation,
    calculate_sensitivity_matrix,
)


def _request() -> ScenarioValuationRequest:
    return ScenarioValuationRequest(
        ticker="acme",
        base_revenue=1000,
        net_debt=100,
        diluted_shares=100,
        forecast_years=2,
        current_share_price=15,
        evidence_ids=["xbrl-revenue", "xbrl-debt", "xbrl-shares"],
        scenarios=[
            ValuationScenarioInput(
                name="bull",
                annual_revenue_growth=0.20,
                terminal_operating_margin=0.25,
                ev_to_operating_income_multiple=15,
            ),
            ValuationScenarioInput(
                name="bear",
                annual_revenue_growth=-0.10,
                terminal_operating_margin=0.10,
                ev_to_operating_income_multiple=8,
            ),
            ValuationScenarioInput(
                name="base",
                annual_revenue_growth=0.05,
                terminal_operating_margin=0.20,
                ev_to_operating_income_multiple=12,
            ),
        ],
    )


def test_calculates_ordered_transparent_scenarios() -> None:
    response = calculate_scenario_valuation(_request())

    assert response.ticker == "ACME"
    assert [scenario.name for scenario in response.scenarios] == [
        "bear",
        "base",
        "bull",
    ]
    base = response.scenarios[1]
    assert base.projected_revenue == pytest.approx(1102.5)
    assert base.projected_operating_income == pytest.approx(220.5)
    assert base.enterprise_value == pytest.approx(2646)
    assert base.equity_value == pytest.approx(2546)
    assert base.implied_share_price == pytest.approx(25.46)
    assert base.upside_downside == pytest.approx(25.46 / 15 - 1)
    assert base.current_price_implied_terminal_margin is not None
    assert "not a forecast" in response.disclaimer


def test_rejects_missing_or_duplicate_scenarios() -> None:
    payload = _request().model_dump()
    payload["scenarios"][2]["name"] = "bull"
    with pytest.raises(ValidationError):
        ScenarioValuationRequest.model_validate(payload)


def test_current_price_is_optional() -> None:
    request = _request().model_copy(update={"current_share_price": None})
    response = calculate_scenario_valuation(request)
    assert all(item.upside_downside is None for item in response.scenarios)
    assert all(item.current_price_implied_terminal_margin is None for item in response.scenarios)


def test_growth_margin_sensitivity_is_monotonic() -> None:
    response = calculate_sensitivity_matrix(
        SensitivityMatrixRequest(
            ticker="ACME",
            kind="growth_margin",
            base_revenue=1000,
            net_debt=100,
            diluted_shares=100,
            forecast_years=1,
            fixed_multiple=10,
            row_values=[0.0, 0.1],
            column_values=[0.1, 0.2],
            current_share_price=10,
        )
    )

    prices = [cell.implied_share_price for cell in response.cells]
    assert prices[1] > prices[0]
    assert prices[2] > prices[0]


def test_margin_multiple_sensitivity_keeps_negative_equity_visible() -> None:
    response = calculate_sensitivity_matrix(
        SensitivityMatrixRequest(
            ticker="ACME",
            kind="margin_multiple",
            base_revenue=100,
            net_debt=10_000,
            diluted_shares=100,
            forecast_years=1,
            row_values=[0.1, 0.2],
            column_values=[5, 10],
        )
    )
    assert all(cell.implied_share_price < 0 for cell in response.cells)


def test_multiple_valuation_exposes_inputs_and_negative_pe_na() -> None:
    response = calculate_multiple_valuation(
        MultipleValuationRequest(
            ticker="ACME",
            method="ev_ebitda",
            share_price=10,
            diluted_shares=100,
            net_debt=200,
            ebitda=100,
            period="TTM 2026Q1",
            evidence_ids=["filing"],
        )
    )
    assert response.value == 12
    assert response.evidence_ids == ["filing"]

    unavailable = calculate_multiple_valuation(
        MultipleValuationRequest(
            ticker="LOSS",
            method="pe",
            share_price=10,
            diluted_shares=100,
            earnings=-20,
            period="TTM 2026Q1",
        )
    )
    assert unavailable.status == "not_available"
    assert unavailable.value is None


def test_discounted_cash_flow_uses_explicit_forecast_and_terminal_spread() -> None:
    response = calculate_discounted_cash_flow(
        DiscountedCashFlowRequest(
            ticker="ACME",
            forecast_free_cash_flows=[100, 110],
            wacc=0.1,
            terminal_growth=0.03,
            net_debt=100,
            diluted_shares=100,
        )
    )
    assert response.enterprise_value > response.present_value_forecast
    assert response.implied_share_price == pytest.approx(
        response.equity_value / 100
    )

    with pytest.raises(ValidationError, match="wacc"):
        DiscountedCashFlowRequest(
            ticker="ACME",
            forecast_free_cash_flows=[100],
            wacc=0.03,
            terminal_growth=0.03,
            net_debt=0,
            diluted_shares=100,
        )
