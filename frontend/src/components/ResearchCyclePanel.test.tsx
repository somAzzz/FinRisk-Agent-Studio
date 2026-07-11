import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { CompanyResearchSnapshot } from "../types";
import { ResearchCyclePanel } from "./ResearchCyclePanel";

vi.mock("../api", () => ({
  api: {
    listResearchAlerts: vi.fn(),
    listPostEarningsDrafts: vi.fn(),
    listTheses: vi.fn(),
    listWatchlist: vi.fn(),
    buildResearchQueue: vi.fn(),
    compareCompanies: vi.fn(),
    listResearchSnapshots: vi.fn(),
    listExpectations: vi.fn(),
    getResearchChanges: vi.fn(),
    startResearchRun: vi.fn(),
    scanWatchlist: vi.fn(),
    saveExpectation: vi.fn(),
    importExpectationsCsv: vi.fn(),
    reviewResearchChange: vi.fn(),
    actOnResearchAlert: vi.fn(),
    createPostEarningsDraft: vi.fn(),
    confirmPostEarningsDraft: vi.fn(),
    listPeerGroups: vi.fn(),
    createPeerGroup: vi.fn(),
    comparePeerGroup: vi.fn(),
    startWorkflow: vi.fn(),
    getStatus: vi.fn(),
  },
}));

const snapshot = (id: string, year: number): CompanyResearchSnapshot => ({
  snapshot_id: id,
  ticker: "ACME",
  period: `${year}Q1`,
  as_of: `${year}-04-30T23:59:59Z`,
  created_at: `${year}-04-30T23:59:59Z`,
  source_fingerprint: `fingerprint-${year}`,
  financials: null,
  management: null,
  risks: [],
  components: [{ component: "financials", state: "complete", source_count: 1 }],
  sources: [{ source_id: `filing-${year}`, source_type: "sec_filing", provider: "SEC", as_of: `${year}-04-20T00:00:00Z`, metadata: {} }],
  warnings: [],
});

describe("ResearchCyclePanel", () => {
  beforeEach(() => {
    vi.mocked(api.listResearchAlerts).mockResolvedValue([]);
    vi.mocked(api.listPostEarningsDrafts).mockResolvedValue([]);
    vi.mocked(api.listTheses).mockResolvedValue([]);
    vi.mocked(api.listWatchlist).mockResolvedValue([]);
    vi.mocked(api.listPeerGroups).mockResolvedValue([]);
    vi.mocked(api.startWorkflow).mockResolvedValue({
      run_id: "workflow-one", status: "completed", started_at: "2026-04-30T00:00:00Z",
    });
    vi.mocked(api.buildResearchQueue).mockResolvedValue({
      entries: [], disclaimer: "Research review only",
    });
    vi.mocked(api.listResearchSnapshots).mockResolvedValue([
      snapshot("new", 2026), snapshot("old", 2025),
    ]);
    vi.mocked(api.listExpectations).mockResolvedValue([]);
    vi.mocked(api.getResearchChanges).mockResolvedValue({
      ticker: "ACME",
      from_snapshot_id: "old",
      to_snapshot_id: "new",
      generated_at: "2026-05-01T00:00:00Z",
      warnings: [],
      changes: [{
        change_id: "change-one", ticker: "ACME", category: "financial",
        key: "revenue:quarter", status: "strengthened", materiality: "high",
        before: { value: 100 }, after: { value: 120 },
        before_evidence_ids: ["filing-2025"], after_evidence_ids: ["filing-2026"],
        detection_method: "deterministic", explanation: "Revenue increased.",
        confidence: 1, analyst_review_status: "unreviewed",
      }],
    });
    vi.mocked(api.startResearchRun).mockResolvedValue({
      manifest: {
        run_id: "research-one", ticker: "ACME", requested_as_of: "2026-04-30T00:00:00Z",
        started_at: "2026-04-30T00:00:00Z", completed_at: "2026-04-30T00:00:01Z",
        state: "partial", snapshot_id: "new", duration_ms: 10, warnings: [],
        components: [{ component: "financials", state: "complete", source_count: 1 }],
      },
      snapshot: snapshot("new", 2026),
    });
  });

  it("creates a snapshot and surfaces evidence-linked changes", async () => {
    render(<ResearchCyclePanel />);
    fireEvent.change(screen.getByLabelText("Research cycle ticker"), { target: { value: "ACME" } });
    fireEvent.click(screen.getByRole("button", { name: "Create snapshot" }));

    await waitFor(() => expect(api.startResearchRun).toHaveBeenCalled());
    expect(await screen.findByText("revenue:quarter")).toBeInTheDocument();
    expect(screen.getByText("Revenue increased.")).toBeInTheDocument();
    expect(screen.getByText("2026Q1")).toBeInTheDocument();
  });

  it("runs a Watchlist scan", async () => {
    vi.mocked(api.scanWatchlist).mockResolvedValue({
      started_at: "2026-04-30T00:00:00Z", completed_at: "2026-04-30T00:00:01Z",
      dry_run: false, results: [],
    });
    render(<ResearchCyclePanel />);
    fireEvent.click(screen.getByRole("button", { name: "Scan watchlist" }));
    await waitFor(() => expect(api.scanWatchlist).toHaveBeenCalledWith({
      minimum_materiality: "medium", max_workers: 2,
    }));
  });

  it("starts FinRisk and links its run to the research snapshot", async () => {
    render(<ResearchCyclePanel />);
    fireEvent.change(screen.getByLabelText("Research cycle ticker"), { target: { value: "ACME" } });
    fireEvent.click(screen.getByRole("button", { name: "Run FinRisk + snapshot" }));

    await waitFor(() => expect(api.startResearchRun).toHaveBeenCalledWith(
      expect.objectContaining({
        ticker: "ACME",
        workflow_run_id: "workflow-one",
        correlation_id: "workflow-one",
      }),
    ));
  });
});
