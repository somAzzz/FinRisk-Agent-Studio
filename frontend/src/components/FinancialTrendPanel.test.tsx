import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { FinancialSnapshot } from "../types";
import { FinancialTrendPanel } from "./FinancialTrendPanel";

const snapshot: FinancialSnapshot = {
  ticker: "AAPL",
  cik: "0000320193",
  company_name: "Apple Inc.",
  as_of: "2026-07-11T00:00:00Z",
  currency: "USD",
  metrics: [
    {
      metric: "revenue",
      value: 400_000_000_000,
      unit: "USD",
      period_end: "2025-12-31",
      period_kind: "ttm",
      fiscal_period: "TTM",
      source_concept: "derived",
      status: "derived",
      derivation: "sum of latest four discrete quarters",
      source_accession_numbers: ["q1", "q2", "q3", "q4"],
    },
  ],
  changes: [
    {
      metric: "revenue",
      change_type: "ttm_yoy",
      current_period_end: "2025-12-31",
      comparison_period_end: "2024-12-31",
      current_value: 400_000_000_000,
      comparison_value: 360_000_000_000,
      absolute_change: 40_000_000_000,
      percent_change: 0.111,
      unit: "USD",
      source_accession_numbers: ["q1", "q2", "q3", "q4"],
    },
  ],
  warnings: ["missing_metric:total_debt"],
};

describe("FinancialTrendPanel", () => {
  it("renders normalized values, changes, lineage, and warnings", () => {
    render(<FinancialTrendPanel snapshot={snapshot} />);
    expect(screen.getByTestId("financial-trend-panel")).toBeInTheDocument();
    expect(screen.getByText("Revenue")).toBeInTheDocument();
    expect(screen.getByText("+11.1% ttm_yoy")).toBeInTheDocument();
    expect(screen.getByText("derived")).toBeInTheDocument();
    expect(screen.getByText("1 data coverage warnings")).toBeInTheDocument();
  });

  it("keeps the report usable when SEC data is unavailable", () => {
    render(
      <FinancialTrendPanel
        snapshot={null}
        error="SEC financial history is unavailable for this run."
      />,
    );
    expect(screen.getByTestId("financial-error")).toHaveTextContent(
      "quantitative cross-check is incomplete",
    );
  });
});
