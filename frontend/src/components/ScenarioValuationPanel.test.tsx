import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { FinancialSnapshot } from "../types";
import { ScenarioValuationPanel } from "./ScenarioValuationPanel";

vi.mock("../api", () => ({
  api: {
    calculateValuation: vi.fn(),
    calculateSensitivity: vi.fn(),
    calculateMultipleValuation: vi.fn(),
    calculateDiscountedCashFlow: vi.fn(),
    listValuationAssumptions: vi.fn().mockResolvedValue([]),
  },
  describeApiError: (_error: unknown, subject: string) => `${subject} could not be loaded.`,
}));

const snapshot: FinancialSnapshot = {
  ticker: "ACME",
  cik: "0000000001",
  as_of: "2026-07-11T00:00:00Z",
  currency: "USD",
  metrics: [
    { metric: "revenue", value: 1000, unit: "USD", period_end: "2025-12-31", period_kind: "ttm", source_concept: "derived", status: "derived", source_accession_numbers: ["revenue"] },
    { metric: "cash", value: 100, unit: "USD", period_end: "2025-12-31", period_kind: "instant", source_concept: "Cash", status: "reported", source_accession_numbers: ["balance"] },
    { metric: "total_debt", value: 200, unit: "USD", period_end: "2025-12-31", period_kind: "instant", source_concept: "derived", status: "derived", source_accession_numbers: ["balance"] },
    { metric: "diluted_shares", value: 100, unit: "shares", period_end: "2025-12-31", period_kind: "annual", source_concept: "Shares", status: "reported", source_accession_numbers: ["shares"] },
  ],
  changes: [],
  warnings: [],
};

describe("ScenarioValuationPanel", () => {
  beforeEach(() => {
    vi.mocked(api.calculateValuation).mockResolvedValue({
      ticker: "ACME", currency: "USD", forecast_years: 2,
      scenarios: [
        { name: "bear", projected_revenue: 900, projected_operating_income: 90, enterprise_value: 900, equity_value: 800, implied_share_price: 8, upside_downside: -0.2, current_price_implied_terminal_margin: 0.11, assumptions: { name: "bear", annual_revenue_growth: -0.05, terminal_operating_margin: 0.1, ev_to_operating_income_multiple: 10 } },
        { name: "base", projected_revenue: 1100, projected_operating_income: 220, enterprise_value: 2640, equity_value: 2540, implied_share_price: 25.4, upside_downside: 1.54, current_price_implied_terminal_margin: 0.08, assumptions: { name: "base", annual_revenue_growth: 0.05, terminal_operating_margin: 0.2, ev_to_operating_income_multiple: 12 } },
        { name: "bull", projected_revenue: 1300, projected_operating_income: 390, enterprise_value: 5850, equity_value: 5750, implied_share_price: 57.5, upside_downside: 4.75, current_price_implied_terminal_margin: 0.05, assumptions: { name: "bull", annual_revenue_growth: 0.15, terminal_operating_margin: 0.3, ev_to_operating_income_multiple: 15 } },
      ],
      evidence_ids: ["revenue", "balance", "shares"],
      methodology: "explicit assumptions",
      disclaimer: "not a forecast, price target, or investment recommendation.",
    });
    vi.mocked(api.calculateSensitivity).mockResolvedValue({
      ticker: "ACME",
      kind: "growth_margin",
      row_label: "annual_revenue_growth",
      column_label: "terminal_operating_margin",
      row_values: [0, 0.05, 0.1],
      column_values: [0.15, 0.2, 0.25],
      cells: [
        { row_value: 0, column_value: 0.15, implied_share_price: 14 },
        { row_value: 0, column_value: 0.2, implied_share_price: 19 },
        { row_value: 0, column_value: 0.25, implied_share_price: 24 },
        { row_value: 0.05, column_value: 0.15, implied_share_price: 15.5 },
        { row_value: 0.05, column_value: 0.2, implied_share_price: 21 },
        { row_value: 0.05, column_value: 0.25, implied_share_price: 26.5 },
        { row_value: 0.1, column_value: 0.15, implied_share_price: 17 },
        { row_value: 0.1, column_value: 0.2, implied_share_price: 23 },
        { row_value: 0.1, column_value: 0.25, implied_share_price: 29 },
      ],
      disclaimer: "analyst-entered assumptions",
    });
    vi.mocked(api.calculateMultipleValuation).mockResolvedValue({ ticker: "ACME", method: "pe", status: "available", value: 5, unit: "x", numerator: 1000, denominator: 200, period: "TTM", evidence_ids: [], methodology: "market cap / earnings", disclaimer: "analyst inputs" });
    vi.mocked(api.calculateDiscountedCashFlow).mockResolvedValue({ ticker: "ACME", present_value_forecast: 180, present_value_terminal: 900, enterprise_value: 1080, equity_value: 980, implied_share_price: 9.8, assumptions: { ticker: "ACME", forecast_free_cash_flows: [100, 110], wacc: 0.1, terminal_growth: 0.03, net_debt: 100, diluted_shares: 100, evidence_ids: [] }, methodology: "discounted explicit cash flows", disclaimer: "analyst inputs" });
  });

  it("calculates a market multiple and DCF from explicit inputs", async () => {
    render(<ScenarioValuationPanel snapshot={snapshot} />);
    fireEvent.click(screen.getByText("Scenario valuation"));
    fireEvent.change(screen.getByLabelText("Current share price"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Valuation earnings"), { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: "Calculate multiple" }));
    await waitFor(() => expect(api.calculateMultipleValuation).toHaveBeenCalled());
    expect(await screen.findByText("5.00x")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Forecast free cash flows"), { target: { value: "100, 110" } });
    fireEvent.change(screen.getByLabelText("DCF WACC"), { target: { value: "0.10" } });
    fireEvent.change(screen.getByLabelText("DCF terminal growth"), { target: { value: "0.03" } });
    fireEvent.click(screen.getByRole("button", { name: "Calculate DCF" }));
    await waitFor(() => expect(api.calculateDiscountedCashFlow).toHaveBeenCalled());
    expect(await screen.findByText("$9.80")).toBeInTheDocument();
  });

  it("prefills only SEC baselines and requires scenario assumptions", async () => {
    render(<ScenarioValuationPanel snapshot={snapshot} />);
    fireEvent.click(screen.getByText("Scenario valuation"));
    expect(screen.getByLabelText("Base revenue")).toHaveValue("1000");
    expect(screen.getByLabelText("Net debt")).toHaveValue("100");
    fireEvent.click(screen.getByRole("button", { name: "Calculate user scenarios" }));
    expect(screen.getByText("Complete every assumption before calculating scenarios.")).toBeInTheDocument();

    for (const [name, values] of Object.entries({
      bear: ["-0.05", "0.10", "10"],
      base: ["0.05", "0.20", "12"],
      bull: ["0.15", "0.30", "15"],
    })) {
      fireEvent.change(screen.getByLabelText(`${name} annual growth`), { target: { value: values[0] } });
      fireEvent.change(screen.getByLabelText(`${name} terminal margin`), { target: { value: values[1] } });
      fireEvent.change(screen.getByLabelText(`${name} multiple`), { target: { value: values[2] } });
    }
    fireEvent.change(screen.getByLabelText("Current share price"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Calculate user scenarios" }));
    await waitFor(() => expect(api.calculateValuation).toHaveBeenCalled());
    expect(await screen.findByText("$25.40")).toBeInTheDocument();
    expect(screen.getByText(/not a forecast/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Build sensitivity matrix" }));
    await waitFor(() => expect(api.calculateSensitivity).toHaveBeenCalled());
    expect(await screen.findByText("$21.00")).toBeInTheDocument();
  });
});
