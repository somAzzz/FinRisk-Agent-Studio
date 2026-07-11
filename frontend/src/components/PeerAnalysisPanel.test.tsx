import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { api } from "../api";
import { PeerAnalysisPanel } from "./PeerAnalysisPanel";

vi.mock("../api", () => ({
  api: {
    listPeerGroups: vi.fn(),
    createPeerGroup: vi.fn(),
    listResearchSnapshots: vi.fn(),
    analyzePeerGroup: vi.fn(),
    suggestPeerCandidates: vi.fn(),
    updatePeerGroup: vi.fn(),
  },
}));

const group = {
  peer_group_id: "peer-one",
  name: "Semiconductors",
  base_ticker: "NVDA",
  members: [
    { ticker: "NVDA", inclusion_reason: "Base company", source: "user" as const, confirmed_by_user: true },
    { ticker: "AMD", inclusion_reason: "Accelerator peer", source: "user" as const, confirmed_by_user: true },
  ],
  industry_template: "semiconductor" as const,
  currency_policy: "no_conversion" as const,
  fiscal_period_policy: "calendarized_ttm" as const,
  user_notes: null,
  created_at: "2026-07-11T00:00:00Z",
  updated_at: "2026-07-11T00:00:00Z",
};

beforeEach(() => {
  vi.mocked(api.listPeerGroups).mockResolvedValue([group]);
  vi.mocked(api.listResearchSnapshots).mockImplementation(async (ticker) => [{
    snapshot_id: `snapshot-${ticker}`,
    ticker,
    period: "2026Q1",
    as_of: "2026-04-30T00:00:00Z",
    created_at: "2026-04-30T00:00:00Z",
    source_fingerprint: ticker,
    risks: [], components: [], sources: [], warnings: [],
  }]);
  vi.mocked(api.analyzePeerGroup).mockResolvedValue({
    financials: {
      as_of: "2026-04-30",
      period_kind: "ttm",
      tickers: ["NVDA", "AMD"],
      values: [{ ticker: "NVDA", metric: "revenue", value: 100, unit: "USD", status: "reported", evidence_ids: ["filing"], freshness_days: 0 }],
      warnings: [],
      disclaimer: "Not a ranking.",
    },
    risks: [{ ticker: "NVDA", total: 1, new: 1, strengthened: 0, weakened: 0, evidence_ids: ["risk"] }],
    expectations: [],
    valuations: [],
    warnings: ["Valuation inputs were not supplied for: AMD, NVDA"],
    disclaimer: "No composite score.",
  });
});

it("loads a confirmed group and compares member snapshots", async () => {
  render(<PeerAnalysisPanel />);

  expect(await screen.findByText((_content, element) => (
    element?.tagName === "LI" && element.textContent?.includes("Accelerator peer") === true
  ))).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Compare peers" }));

  await waitFor(() => expect(api.analyzePeerGroup).toHaveBeenCalled());
  expect(await screen.findByText("100 USD")).toBeInTheDocument();
  expect(screen.getByText("0d")).toBeInTheDocument();
});
