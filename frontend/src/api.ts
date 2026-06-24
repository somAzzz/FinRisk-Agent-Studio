// Thin API client for the FinRisk backend.
// All requests go to /workflows/* which the Vite dev server proxies to
// http://127.0.0.1:8000 (see vite.config.ts). In production the same
// paths can be served behind a reverse proxy.

import type {
  FinRiskRequest,
  WorkflowReportResponse,
  WorkflowRunSummary,
  WorkflowStatusResponse,
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
  health(): Promise<{ status: string; runs: number }> {
    return sendRequest<{ status: string; runs: number }>("/workflows/health");
  },
};

export const apiPaths = {
  startWorkflow: "/workflows/finrisk/run",
  status: (runId: string) => `/workflows/${runId}`,
  report: (runId: string) => `/workflows/${runId}/report`,
  health: "/workflows/health",
};
