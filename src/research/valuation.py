"""Transparent scenario valuation based exclusively on user assumptions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScenarioName = Literal["bear", "base", "bull"]
SensitivityKind = Literal["growth_margin", "margin_multiple"]
ValuationMethod = Literal["pe", "ev_ebitda", "fcf_yield"]


class ValuationScenarioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ScenarioName
    annual_revenue_growth: float = Field(ge=-1.0, le=3.0)
    terminal_operating_margin: float = Field(ge=-1.0, le=1.0)
    ev_to_operating_income_multiple: float = Field(gt=0.0, le=100.0)


class ScenarioValuationRequest(BaseModel):
    """Inputs are assumptions supplied by the analyst, never extracted claims."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    currency: str = "USD"
    base_revenue: float = Field(gt=0.0)
    net_debt: float
    diluted_shares: float = Field(gt=0.0)
    forecast_years: int = Field(ge=1, le=10)
    current_share_price: float | None = Field(default=None, gt=0.0)
    scenarios: list[ValuationScenarioInput] = Field(min_length=3, max_length=3)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _exact_scenarios(self) -> ScenarioValuationRequest:
        names = [scenario.name for scenario in self.scenarios]
        if set(names) != {"bear", "base", "bull"}:
            raise ValueError("scenarios must contain one bear, base, and bull case")
        if len(names) != len(set(names)):
            raise ValueError("scenario names must be unique")
        return self


class ScenarioValuationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ScenarioName
    projected_revenue: float
    projected_operating_income: float
    enterprise_value: float
    equity_value: float
    implied_share_price: float
    upside_downside: float | None = None
    current_price_implied_terminal_margin: float | None = None
    assumptions: ValuationScenarioInput


class ScenarioValuationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    currency: str
    forecast_years: int
    scenarios: list[ScenarioValuationResult]
    evidence_ids: list[str] = Field(default_factory=list)
    methodology: str
    disclaimer: str


class SensitivityMatrixRequest(BaseModel):
    """Two-dimensional valuation grid using only explicit analyst inputs."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    kind: SensitivityKind
    base_revenue: float = Field(gt=0.0)
    net_debt: float
    diluted_shares: float = Field(gt=0.0)
    forecast_years: int = Field(ge=1, le=10)
    fixed_growth: float = Field(default=0.0, ge=-1.0, le=3.0)
    fixed_margin: float = Field(default=0.1, ge=-1.0, le=1.0)
    fixed_multiple: float = Field(default=10.0, gt=0.0, le=100.0)
    row_values: list[float] = Field(min_length=2, max_length=25)
    column_values: list[float] = Field(min_length=2, max_length=25)
    current_share_price: float | None = Field(default=None, gt=0.0)


class SensitivityCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_value: float
    column_value: float
    implied_share_price: float
    upside_downside: float | None = None


class SensitivityMatrixResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    kind: SensitivityKind
    row_label: str
    column_label: str
    row_values: list[float]
    column_values: list[float]
    cells: list[SensitivityCell]
    disclaimer: str


class MultipleValuationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    method: ValuationMethod
    share_price: float = Field(gt=0)
    diluted_shares: float = Field(gt=0)
    net_debt: float = 0
    earnings: float | None = None
    ebitda: float | None = None
    free_cash_flow: float | None = None
    period: str
    evidence_ids: list[str] = Field(default_factory=list)


class MultipleValuationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    method: ValuationMethod
    status: Literal["available", "not_available"]
    value: float | None = None
    unit: Literal["x", "percent"]
    numerator: float
    denominator: float | None = None
    reason: str | None = None
    period: str
    evidence_ids: list[str]
    methodology: str
    disclaimer: str


class DiscountedCashFlowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    forecast_free_cash_flows: list[float] = Field(min_length=1, max_length=10)
    wacc: float = Field(gt=0, le=1)
    terminal_growth: float = Field(ge=-0.2, le=0.2)
    net_debt: float
    diluted_shares: float = Field(gt=0)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _valid_terminal_spread(self) -> DiscountedCashFlowRequest:
        if self.wacc <= self.terminal_growth:
            raise ValueError("wacc must exceed terminal_growth")
        return self


class DiscountedCashFlowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    present_value_forecast: float
    present_value_terminal: float
    enterprise_value: float
    equity_value: float
    implied_share_price: float
    assumptions: DiscountedCashFlowRequest
    methodology: str
    disclaimer: str


def calculate_scenario_valuation(
    request: ScenarioValuationRequest,
) -> ScenarioValuationResponse:
    """Calculate EV/operating-income scenarios with no hidden assumptions."""
    results: list[ScenarioValuationResult] = []
    current_enterprise_value = None
    if request.current_share_price is not None:
        current_enterprise_value = request.current_share_price * request.diluted_shares + request.net_debt

    for scenario in request.scenarios:
        projected_revenue = request.base_revenue * (1.0 + scenario.annual_revenue_growth) ** request.forecast_years
        projected_operating_income = projected_revenue * scenario.terminal_operating_margin
        enterprise_value = projected_operating_income * scenario.ev_to_operating_income_multiple
        equity_value = enterprise_value - request.net_debt
        implied_share_price = equity_value / request.diluted_shares
        upside_downside = (
            implied_share_price / request.current_share_price - 1.0 if request.current_share_price is not None else None
        )
        implied_margin = (
            current_enterprise_value / projected_revenue / scenario.ev_to_operating_income_multiple
            if current_enterprise_value is not None
            else None
        )
        results.append(
            ScenarioValuationResult(
                name=scenario.name,
                projected_revenue=projected_revenue,
                projected_operating_income=projected_operating_income,
                enterprise_value=enterprise_value,
                equity_value=equity_value,
                implied_share_price=implied_share_price,
                upside_downside=upside_downside,
                current_price_implied_terminal_margin=implied_margin,
                assumptions=scenario,
            )
        )

    order = {"bear": 0, "base": 1, "bull": 2}
    results.sort(key=lambda result: order[result.name])
    return ScenarioValuationResponse(
        ticker=request.ticker.upper().strip(),
        currency=request.currency.upper().strip(),
        forecast_years=request.forecast_years,
        scenarios=results,
        evidence_ids=request.evidence_ids,
        methodology=(
            "Projected revenue * terminal operating margin * "
            "EV/operating-income multiple, less net debt, divided by diluted shares."
        ),
        disclaimer=(
            "Scenario output based solely on analyst-entered assumptions; "
            "it is not a forecast, price target, or investment recommendation."
        ),
    )


def calculate_sensitivity_matrix(
    request: SensitivityMatrixRequest,
) -> SensitivityMatrixResponse:
    if request.kind == "growth_margin":
        row_label = "annual_revenue_growth"
        column_label = "terminal_operating_margin"
    else:
        row_label = "terminal_operating_margin"
        column_label = "ev_to_operating_income_multiple"
    cells: list[SensitivityCell] = []
    for row in request.row_values:
        for column in request.column_values:
            if request.kind == "growth_margin":
                growth, margin, multiple = row, column, request.fixed_multiple
                if not -1.0 <= growth <= 3.0 or not -1.0 <= margin <= 1.0:
                    raise ValueError("growth or margin sensitivity value is out of range")
            else:
                growth, margin, multiple = request.fixed_growth, row, column
                if not -1.0 <= margin <= 1.0 or not 0.0 < multiple <= 100.0:
                    raise ValueError("margin or multiple sensitivity value is out of range")
            projected_revenue = request.base_revenue * (1.0 + growth) ** request.forecast_years
            equity_value = projected_revenue * margin * multiple - request.net_debt
            implied_price = equity_value / request.diluted_shares
            upside = (
                implied_price / request.current_share_price - 1.0 if request.current_share_price is not None else None
            )
            cells.append(
                SensitivityCell(
                    row_value=row,
                    column_value=column,
                    implied_share_price=implied_price,
                    upside_downside=upside,
                )
            )
    return SensitivityMatrixResponse(
        ticker=request.ticker.upper().strip(),
        kind=request.kind,
        row_label=row_label,
        column_label=column_label,
        row_values=request.row_values,
        column_values=request.column_values,
        cells=cells,
        disclaimer=(
            "Sensitivity output is based solely on analyst-entered assumptions; "
            "it is not a forecast, price target, or investment recommendation."
        ),
    )


def calculate_multiple_valuation(
    request: MultipleValuationRequest,
) -> MultipleValuationResponse:
    market_cap = request.share_price * request.diluted_shares
    denominator: float | None
    numerator: float
    unit: Literal["x", "percent"]
    if request.method == "pe":
        numerator, denominator, unit = market_cap, request.earnings, "x"
        methodology = "market capitalization / trailing or forward earnings"
        invalid_reason = "earnings must be positive for P/E"
    elif request.method == "ev_ebitda":
        numerator, denominator, unit = market_cap + request.net_debt, request.ebitda, "x"
        methodology = "(market capitalization + net debt) / EBITDA"
        invalid_reason = "EBITDA must be positive for EV/EBITDA"
    else:
        numerator, denominator, unit = request.free_cash_flow or 0, market_cap, "percent"
        methodology = "equity free cash flow / market capitalization"
        invalid_reason = "free_cash_flow must be supplied for FCF yield"
    available = denominator is not None and denominator > 0
    if request.method == "fcf_yield" and request.free_cash_flow is None:
        available = False
    value = numerator / denominator if available else None
    return MultipleValuationResponse(
        ticker=request.ticker.upper().strip(),
        method=request.method,
        status="available" if available else "not_available",
        value=value,
        unit=unit,
        numerator=numerator,
        denominator=denominator,
        reason=None if available else invalid_reason,
        period=request.period,
        evidence_ids=request.evidence_ids,
        methodology=methodology,
        disclaimer="Mechanical valuation output, not an investment recommendation.",
    )


def calculate_discounted_cash_flow(
    request: DiscountedCashFlowRequest,
) -> DiscountedCashFlowResponse:
    present_value_forecast = sum(
        cash_flow / (1 + request.wacc) ** year
        for year, cash_flow in enumerate(request.forecast_free_cash_flows, start=1)
    )
    final_cash_flow = request.forecast_free_cash_flows[-1]
    terminal_value = (
        final_cash_flow
        * (1 + request.terminal_growth)
        / (request.wacc - request.terminal_growth)
    )
    present_value_terminal = terminal_value / (
        (1 + request.wacc) ** len(request.forecast_free_cash_flows)
    )
    enterprise_value = present_value_forecast + present_value_terminal
    equity_value = enterprise_value - request.net_debt
    return DiscountedCashFlowResponse(
        ticker=request.ticker.upper().strip(),
        present_value_forecast=present_value_forecast,
        present_value_terminal=present_value_terminal,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        implied_share_price=equity_value / request.diluted_shares,
        assumptions=request,
        methodology="Explicit FCF forecast plus Gordon-growth terminal value, discounted at WACC.",
        disclaimer="DCF output depends entirely on analyst assumptions; it is not a price target.",
    )


__all__ = [
    "DiscountedCashFlowRequest",
    "DiscountedCashFlowResponse",
    "MultipleValuationRequest",
    "MultipleValuationResponse",
    "ScenarioValuationRequest",
    "ScenarioValuationResponse",
    "ScenarioValuationResult",
    "SensitivityCell",
    "SensitivityMatrixRequest",
    "SensitivityMatrixResponse",
    "ValuationScenarioInput",
    "calculate_discounted_cash_flow",
    "calculate_multiple_valuation",
    "calculate_scenario_valuation",
    "calculate_sensitivity_matrix",
]
