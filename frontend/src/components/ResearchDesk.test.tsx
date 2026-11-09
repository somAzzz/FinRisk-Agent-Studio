import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { TodayDashboard } from "./TodayDashboard";
import { valuationsFrom, type Assumption } from "./PeerValuationInputs";

it("opens the filing that needs review without suggesting a deadline or an unrelated issuer", () => {
  const filing = {
    kind: "filing" as const,
    runId: "case",
    status: "needs_review",
    title: "Example issuer",
  };
  const select = vi.fn();
  render(
    <TodayDashboard
      staticMode={false}
      historyItems={[
        {
          kind: "finrisk",
          runId: "other",
          title: "Other study",
          status: "completed",
        },
        filing,
      ]}
      onSelect={select}
      onStartResearch={() => {}}
      onOpenRuns={() => {}}
    />,
  );
  const card = screen
    .getByRole("button", { name: "Review" })
    .closest("article")!;
  expect(within(card).getByText(filing.title)).toBeVisible();
  fireEvent.click(within(card).getByRole("button"));
  expect(select).toHaveBeenCalledWith(filing);
  expect(screen.queryByText(/Jul 13|AAPL/)).toBeNull();
});
it("preserves missing valuation inputs instead of treating blanks as zero", () => {
  const input: Assumption = {
    id: "one",
    ticker: "ACME",
    method: "ev_ebitda",
    price: "2",
    shares: "3",
    denominator: "4",
    debt: "",
    evidence: "filing-p10, note-3",
    period: "FY26",
  };
  expect(() => valuationsFrom([input])).toThrow(/net debt/);
  expect(valuationsFrom([{ ...input, debt: "-1" }])).toEqual([
    {
      ticker: "ACME",
      method: "ev_ebitda",
      share_price: 2,
      diluted_shares: 3,
      ebitda: 4,
      net_debt: -1,
      evidence_ids: ["filing-p10", "note-3"],
      period: "FY26",
    },
  ]);
});
