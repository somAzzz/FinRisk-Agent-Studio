// Thin API client for the FinRisk backend.
// All requests go to /workflows/* which the Vite dev server proxies to
// http://127.0.0.1:8000 (see vite.config.ts). In production the same
// paths can be served behind a reverse proxy.

import type {
  AgentHumanReviewItemWire,
  AgentReviewActionRequest,
  AgentRunRequest,
  AgentRunSummary,
  AgentRunTimelineResponse,
  AgentRunTraceResponse,
  FinRiskRequest,
  FinancialSnapshot,
  InvestmentThesis,
  ManagementComparisonResponse,
  ResearchReminder,
  ScenarioValuationRequest,
  ScenarioValuationResponse,
  ThesisReview,
  WatchlistItem,
  WorkflowArtifactsResponse,
  WorkflowChunksResponse,
  WorkflowEvaluationResponse,
  WorkflowGraphResponse,
  WorkflowLifecyclesResponse,
  WorkflowLLMLogResponse,
  WorkflowReportResponse,
  WorkflowRunSummary,
  WorkflowSectionsResponse,
  WorkflowStatusResponse,
  WorkflowTraceResponse,
} from "./types";

const DEFAULT_BASE = "";

export class FinRiskApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "FinRiskApiError";
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${DEFAULT_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = await response.text().catch(() => null);
    }
    throw new FinRiskApiError(
      `Request failed: ${response.status} ${response.statusText}`,
      response.status,
      body,
    );
  }
  return (await response.json()) as T;
}

// Alias avoids shadowing the global `fetch` and `request` types when
// referenced through bundlers' auto-imports.
const sendRequest = request;

export const api = {
  startWorkflow(req: FinRiskRequest): Promise<WorkflowRunSummary> {
    return sendRequest<WorkflowRunSummary>("/workflows/finrisk/run", {
      method: "POST",
      body: JSON.stringify(req),
    });
  },
  getStatus(runId: string): Promise<WorkflowStatusResponse> {
    return sendRequest<WorkflowStatusResponse>(`/workflows/${runId}`);
  },
  getReport(runId: string): Promise<WorkflowReportResponse> {
    return sendRequest<WorkflowReportResponse>(`/workflows/${runId}/report`);
  },
  getTrace(runId: string): Promise<WorkflowTraceResponse> {
    return sendRequest<WorkflowTraceResponse>(`/workflows/${runId}/trace`);
  },
  getLLMLog(runId: string): Promise<WorkflowLLMLogResponse> {
    return sendRequest<WorkflowLLMLogResponse>(
      `/workflows/${runId}/llm_log`,
    );
  },
  getChunks(runId: string): Promise<WorkflowChunksResponse> {
    return sendRequest<WorkflowChunksResponse>(`/workflows/${runId}/chunks`);
  },
  getSections(runId: string): Promise<WorkflowSectionsResponse> {
    return sendRequest<WorkflowSectionsResponse>(
      `/workflows/${runId}/sections`,
    );
  },
  getLifecycles(runId: string): Promise<WorkflowLifecyclesResponse> {
    return sendRequest<WorkflowLifecyclesResponse>(
      `/workflows/${runId}/lifecycles`,
    );
  },
  getGraph(runId: string): Promise<WorkflowGraphResponse> {
    return sendRequest<WorkflowGraphResponse>(`/workflows/${runId}/graph`);
  },
  getEvaluation(runId: string): Promise<WorkflowEvaluationResponse> {
    return sendRequest<WorkflowEvaluationResponse>(
      `/workflows/${runId}/evaluation`,
    );
  },
  getArtifacts(runId: string): Promise<WorkflowArtifactsResponse> {
    return sendRequest<WorkflowArtifactsResponse>(
      `/workflows/${runId}/artifacts`,
    );
  },
  health(): Promise<{ status: string; runs: number }> {
    return sendRequest<{ status: string; runs: number }>("/workflows/health");
  },
  listWorkflows(limit = 20): Promise<WorkflowRunSummary[]> {
    return sendRequest<WorkflowRunSummary[]>(`/workflows?limit=${limit}`);
  },
  getFinancialSnapshot(
    ticker: string,
    asOf?: string,
  ): Promise<FinancialSnapshot> {
    const query = asOf ? `?as_of=${encodeURIComponent(asOf)}` : "";
    return sendRequest<FinancialSnapshot>(
      `/research/financials/${encodeURIComponent(ticker)}${query}`,
    );
  },
  calculateValuation(
    valuation: ScenarioValuationRequest,
  ): Promise<ScenarioValuationResponse> {
    return sendRequest<ScenarioValuationResponse>(
      "/research/valuation/scenarios",
      { method: "POST", body: JSON.stringify(valuation) },
    );
  },
  getManagementComparison(
    ticker: string,
    year: number,
    quarter: number,
    compareYear?: number,
    compareQuarter?: number,
  ): Promise<ManagementComparisonResponse> {
    const params = new URLSearchParams({ year: String(year), quarter: String(quarter) });
    if (compareYear != null && compareQuarter != null) {
      params.set("compare_year", String(compareYear));
      params.set("compare_quarter", String(compareQuarter));
    }
    return sendRequest<ManagementComparisonResponse>(
      `/research/management/${encodeURIComponent(ticker)}?${params.toString()}`,
    );
  },
  listTheses(ticker?: string): Promise<InvestmentThesis[]> {
    const query = ticker ? `?ticker=${encodeURIComponent(ticker)}` : "";
    return sendRequest<InvestmentThesis[]>(`/research/theses${query}`);
  },
  saveThesis(thesis: InvestmentThesis): Promise<InvestmentThesis> {
    return sendRequest<InvestmentThesis>("/research/theses", {
      method: "POST",
      body: JSON.stringify(thesis),
    });
  },
  reviewThesis(
    thesisId: string,
    review: ThesisReview,
  ): Promise<InvestmentThesis> {
    return sendRequest<InvestmentThesis>(
      `/research/theses/${encodeURIComponent(thesisId)}/reviews`,
      { method: "POST", body: JSON.stringify(review) },
    );
  },
  listWatchlist(): Promise<WatchlistItem[]> {
    return sendRequest<WatchlistItem[]>("/research/watchlist");
  },
  listResearchReminders(): Promise<ResearchReminder[]> {
    return sendRequest<ResearchReminder[]>("/research/reminders");
  },
  saveWatchlistItem(item: WatchlistItem): Promise<WatchlistItem> {
    return sendRequest<WatchlistItem>(
      `/research/watchlist/${encodeURIComponent(item.ticker)}`,
      { method: "PUT", body: JSON.stringify(item) },
    );
  },
  // v18 supply chain
  listSupplyChains(
    limit = 20,
  ): Promise<import("./supply-chain-types").SupplyChainExploreResponseWire[]> {
    return sendRequest(`/supply-chain?limit=${limit}`);
  },
  startSupplyChain(
    req: import("./supply-chain-types").SupplyChainExploreRequestWire,
  ): Promise<import("./supply-chain-types").SupplyChainExploreResponseWire> {
    return sendRequest<
      import("./supply-chain-types").SupplyChainExploreResponseWire
    >("/supply-chain/explore", {
      method: "POST",
      body: JSON.stringify(req),
    });
  },
  getSupplyChainSankey(
    runId: string,
  ): Promise<{ run_id: string; sankey: import("./supply-chain-types").SupplyChainSankeyPayloadWire | null }> {
    return sendRequest(`/supply-chain/${runId}/sankey`);
  },
  getSupplyChainStatus(
    runId: string,
  ): Promise<import("./supply-chain-types").SupplyChainStatusResponseWire> {
    return sendRequest(`/supply-chain/${runId}`);
  },
  expandSupplyChain(
    req: import("./supply-chain-types").SupplyChainExpandRequestWire,
  ): Promise<import("./supply-chain-types").SupplyChainExploreResponseWire> {
    return sendRequest<
      import("./supply-chain-types").SupplyChainExploreResponseWire
    >("/supply-chain/expand", {
      method: "POST",
      body: JSON.stringify(req),
    });
  },
  // v21 LLM-driven agent runs
  listAgentRuns(limit = 20): Promise<AgentRunSummary[]> {
    return sendRequest<AgentRunSummary[]>(`/agent-runs?limit=${limit}`);
  },
  startAgentRun(req: AgentRunRequest): Promise<AgentRunSummary> {
    return sendRequest<AgentRunSummary>("/agent-runs", {
      method: "POST",
      body: JSON.stringify(req),
    });
  },
  getAgentRunTimeline(runId: string): Promise<AgentRunTimelineResponse> {
    return sendRequest<AgentRunTimelineResponse>(
      `/agent-runs/${runId}/timeline`,
    );
  },
  getAgentRunTrace(runId: string): Promise<AgentRunTraceResponse> {
    return sendRequest<AgentRunTraceResponse>(
      `/agent-runs/${runId}/trace.json`,
    );
  },
  reviewAgentRunItem(
    runId: string,
    itemId: string,
    req: AgentReviewActionRequest,
  ): Promise<AgentHumanReviewItemWire> {
    return sendRequest<AgentHumanReviewItemWire>(
      `/agent-runs/${runId}/review-items/${itemId}`,
      {
        method: "POST",
        body: JSON.stringify(req),
      },
    );
  },
  reviewAgentRunCandidate(
    runId: string,
    candidateId: string,
    req: AgentReviewActionRequest,
  ): Promise<import("./types").AgentEvidenceCandidateWire> {
    return sendRequest<import("./types").AgentEvidenceCandidateWire>(
      `/agent-runs/${runId}/evidence-candidates/${candidateId}`,
      {
        method: "POST",
        body: JSON.stringify(req),
      },
    );
  },
};

export const apiPaths = {
  startWorkflow: "/workflows/finrisk/run",
  status: (runId: string) => `/workflows/${runId}`,
  report: (runId: string) => `/workflows/${runId}/report`,
  trace: (runId: string) => `/workflows/${runId}/trace`,
  graph: (runId: string) => `/workflows/${runId}/graph`,
  evaluation: (runId: string) => `/workflows/${runId}/evaluation`,
  artifacts: (runId: string) => `/workflows/${runId}/artifacts`,
  health: "/workflows/health",
  workflowHistory: "/workflows",
  financialSnapshot: (ticker: string) => `/research/financials/${ticker}`,
  theses: "/research/theses",
  watchlist: "/research/watchlist",
  agentRunHistory: "/agent-runs",
  supplyChainHistory: "/supply-chain",
  startSupplyChain: "/supply-chain/explore",
  expandSupplyChain: "/supply-chain/expand",
  supplyChainStatus: (runId: string) => `/supply-chain/${runId}`,
  supplyChainSankey: (runId: string) => `/supply-chain/${runId}/sankey`,
  startAgentRun: "/agent-runs",
  agentRunTimeline: (runId: string) => `/agent-runs/${runId}/timeline`,
  agentRunTrace: (runId: string) => `/agent-runs/${runId}/trace.json`,
  agentRunReviewItem: (runId: string, itemId: string) =>
    `/agent-runs/${runId}/review-items/${itemId}`,
  agentRunReviewCandidate: (runId: string, candidateId: string) =>
    `/agent-runs/${runId}/evidence-candidates/${candidateId}`,
};
