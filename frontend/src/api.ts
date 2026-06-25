// Thin API client for the FinRisk backend.
// All requests go to /workflows/* which the Vite dev server proxies to
// http://127.0.0.1:8000 (see vite.config.ts). In production the same
// paths can be served behind a reverse proxy.

import type {
  FinRiskRequest,
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
  // v18 supply chain
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
  startSupplyChain: "/supply-chain/explore",
  expandSupplyChain: "/supply-chain/expand",
  supplyChainStatus: (runId: string) => `/supply-chain/${runId}`,
  supplyChainSankey: (runId: string) => `/supply-chain/${runId}/sankey`,
};
