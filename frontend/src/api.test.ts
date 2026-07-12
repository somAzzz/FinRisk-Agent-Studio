import { describe, expect, it, vi, beforeEach } from "vitest";
import { api, clearApiCache, describeApiError, FinRiskApiError } from "./api";
import type {
  FinRiskRequest,
  WorkflowReportResponse,
  WorkflowRunSummary,
  WorkflowStatusResponse,
} from "./types";

const SUMMARY: WorkflowRunSummary = {
  run_id: "run-abc",
  status: "queued",
  started_at: "2026-06-20T00:00:00.000Z",
  report_url: "/workflows/run-abc/report",
};

const STATUS: WorkflowStatusResponse = {
  run_id: "run-abc",
  status: "completed",
  trace: [
    {
      step_name: "company_resolver",
      status: "completed",
      started_at: "2026-06-20T00:00:00.000Z",
      completed_at: "2026-06-20T00:00:00.100Z",
    },
  ],
  company: null,
  risk_count: 0,
  evidence_count: 0,
  evaluation: null,
};

const REPORT: WorkflowReportResponse = {
  run_id: "run-abc",
  status: "completed",
  report: null,
  report_v16: null,
  markdown: null,
  evaluation: null,
};

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearApiCache();
  });

  it("posts FinRiskRequest to /workflows/finrisk/run", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => SUMMARY,
    });
    vi.stubGlobal("fetch", fetchMock);

    const req: FinRiskRequest = {
      ticker: "AAPL",
      analysis_goal: "test",
      demo_mode: true,
    };
    const result = await api.startWorkflow(req);
    expect(result).toEqual(SUMMARY);
    expect(fetchMock).toHaveBeenCalledWith(
      "/workflows/finrisk/run",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(req),
      }),
    );
  });

  it("fetches status from /workflows/{run_id}", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => STATUS,
    });
    vi.stubGlobal("fetch", fetchMock);
    const result = await api.getStatus("run-abc");
    expect(result.run_id).toBe("run-abc");
    expect(fetchMock).toHaveBeenCalledWith("/workflows/run-abc", expect.any(Object));
  });

  it("fetches report from /workflows/{run_id}/report", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => REPORT,
    });
    vi.stubGlobal("fetch", fetchMock);
    const result = await api.getReport("run-abc");
    expect(result).toEqual(REPORT);
    expect(fetchMock).toHaveBeenCalledWith(
      "/workflows/run-abc/report",
      expect.any(Object),
    );
  });

  it("fetches a point-in-time financial snapshot", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ticker: "AAPL", metrics: [], changes: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await api.getFinancialSnapshot("AAPL", "2025-12-31");
    expect(fetchMock).toHaveBeenCalledWith(
      "/research/financials/AAPL?as_of=2025-12-31",
      expect.any(Object),
    );
  });

  it("posts only explicit scenario valuation assumptions", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ scenarios: [] }) });
    vi.stubGlobal("fetch", fetchMock);
    const request = {
      ticker: "ACME", currency: "USD", base_revenue: 1000, net_debt: 0,
      diluted_shares: 100, forecast_years: 2, evidence_ids: [],
      scenarios: [
        { name: "bear" as const, annual_revenue_growth: 0, terminal_operating_margin: 0.1, ev_to_operating_income_multiple: 10 },
        { name: "base" as const, annual_revenue_growth: 0.1, terminal_operating_margin: 0.2, ev_to_operating_income_multiple: 12 },
        { name: "bull" as const, annual_revenue_growth: 0.2, terminal_operating_margin: 0.3, ev_to_operating_income_multiple: 15 },
      ],
    };
    await api.calculateValuation(request);
    expect(fetchMock).toHaveBeenCalledWith(
      "/research/valuation/scenarios",
      expect.objectContaining({ method: "POST", body: JSON.stringify(request) }),
    );
  });

  it("fetches due research reminders", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);
    await api.listResearchReminders();
    expect(fetchMock).toHaveBeenCalledWith("/research/reminders", expect.any(Object));
  });

  it("starts a point-in-time research run", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ manifest: {} }) });
    vi.stubGlobal("fetch", fetchMock);
    const input = { ticker: "AAPL", year: 2026, quarter: 2 };
    await api.startResearchRun(input);
    expect(fetchMock).toHaveBeenCalledWith(
      "/research/runs",
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) }),
    );
  });

  it("runs the incremental Watchlist scanner", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ results: [] }) });
    vi.stubGlobal("fetch", fetchMock);
    const input = { minimum_materiality: "medium" as const, dry_run: true };
    await api.scanWatchlist(input);
    expect(fetchMock).toHaveBeenCalledWith(
      "/research/monitor/scan",
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) }),
    );
  });

  it("compares a point-in-time expectation with a saved actual", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ absolute_surprise: 5 }) });
    vi.stubGlobal("fetch", fetchMock);
    await api.compareExpectation("expectation-one", "snapshot-one");
    expect(fetchMock).toHaveBeenCalledWith(
      "/research/expectations/expectation-one/compare?snapshot_id=snapshot-one",
      expect.any(Object),
    );
  });

  it("raises FinRiskApiError on non-2xx responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: async () => ({ detail: "unknown run" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.getStatus("run-x")).rejects.toBeInstanceOf(FinRiskApiError);
  });

  it("deduplicates simultaneous GET requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => STATUS });
    vi.stubGlobal("fetch", fetchMock);
    const [left, right] = await Promise.all([api.getStatus("run-shared"), api.getStatus("run-shared")]);
    expect(left).toEqual(right);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("exposes Retry-After and actionable rate-limit copy", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      statusText: "Too Many Requests",
      headers: new Headers({ "Retry-After": "12" }),
      json: async () => ({ detail: "Rate limit exceeded." }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const error = await api.getStatus("run-rate-limited").then(
      () => { throw new Error("expected rate limit"); },
      (value) => value as FinRiskApiError,
    );
    expect(error.retryAfterSeconds).toBe(12);
    expect(describeApiError(error, "Run status")).toContain("Wait 12 seconds");
  });

  it("calls every advanced valuation endpoint and peer deletion", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    await api.calculateMultipleValuation({ ticker: "ACME", method: "pe", share_price: 10, diluted_shares: 10, net_debt: 0, earnings: 20, period: "TTM", evidence_ids: [] });
    await api.calculateDiscountedCashFlow({ ticker: "ACME", forecast_free_cash_flows: [10, 11], wacc: 0.1, terminal_growth: 0.03, net_debt: 0, diluted_shares: 10, evidence_ids: [] });
    await api.listValuationAssumptions("ACME", 20);
    fetchMock.mockResolvedValueOnce({ ok: true, status: 204, json: async () => undefined });
    await api.deletePeerGroup("peer-one");
    expect(fetchMock).toHaveBeenCalledWith("/research/valuation/multiple", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenCalledWith("/research/valuation/dcf", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenCalledWith("/research/valuation/history/ACME?limit=20", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/research/peer-groups/peer-one", expect.objectContaining({ method: "DELETE" }));
  });

  it("fetches v16 trace from /workflows/{run_id}/trace", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: "run-abc",
        trace: [],
        fallback_events: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await api.getTrace("run-abc");
    expect(fetchMock).toHaveBeenCalledWith(
      "/workflows/run-abc/trace",
      expect.any(Object),
    );
  });

  it("fetches v16 graph from /workflows/{run_id}/graph", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        nodes: [],
        edges: [],
        paths: [],
        insights: [],
        guardrail_findings: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await api.getGraph("run-abc");
    expect(fetchMock).toHaveBeenCalledWith(
      "/workflows/run-abc/graph",
      expect.any(Object),
    );
  });

  it("fetches v16 evaluation from /workflows/{run_id}/evaluation", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: "run-abc",
        final_status: "pass",
        step_evaluations: [],
        overall_metrics: {},
        blocker_count: 0,
        warning_count: 0,
        unsupported_claims: [],
        human_review_required: false,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await api.getEvaluation("run-abc");
    expect(fetchMock).toHaveBeenCalledWith(
      "/workflows/run-abc/evaluation",
      expect.any(Object),
    );
  });

  it("posts V21 agent run requests to /agent-runs", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: "agent-abc",
        status: "completed",
        timeline_url: "/agent-runs/agent-abc/timeline",
        trace_url: "/agent-runs/agent-abc/trace.json",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.startAgentRun({
      goal: "Find Apple supply chain evidence",
      workflow_kind: "finrisk",
      provider: "deepseek",
      tool_loop_mode: "auto",
      tool_scope: "finrisk_market",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/agent-runs",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("fetches V21 agent run timeline and trace", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: "agent-abc",
        status: "completed",
        decisions: [],
        subgoals: [],
        tool_events: [],
        evidence_candidates: [],
        human_review_items: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.getAgentRunTimeline("agent-abc");
    await api.getAgentRunTrace("agent-abc");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/agent-runs/agent-abc/timeline",
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/agent-runs/agent-abc/trace.json",
      expect.any(Object),
    );
  });

  it("posts V21 human review actions", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        item_id: "hri-1",
        run_id: "agent-abc",
        object_type: "evidence_candidate",
        object_id: "ev-1",
        reason: "needs source inspection",
        suggested_action: "inspect_source",
        status: "approved",
        created_at: "2026-06-27T00:00:00.000Z",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.reviewAgentRunItem("agent-abc", "hri-1", { action: "approve" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/agent-runs/agent-abc/review-items/hri-1",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ action: "approve" }),
      }),
    );
  });
});
