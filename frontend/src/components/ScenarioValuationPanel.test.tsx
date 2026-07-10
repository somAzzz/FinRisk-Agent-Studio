import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { FinancialSnapshot } from "../types";
import { ScenarioValuationPanel } from "./ScenarioValuationPanel";

vi.mock("../api", () => ({ api: { calculateValuation: vi.fn() } }));

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
  });
});
