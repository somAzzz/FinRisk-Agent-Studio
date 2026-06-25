import { describe, expect, it, vi, beforeEach } from "vitest";
import { api, FinRiskApiError } from "./api";
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
});
