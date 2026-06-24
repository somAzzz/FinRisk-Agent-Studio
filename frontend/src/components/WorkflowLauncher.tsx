import { useState } from "react";
import { api, FinRiskApiError } from "../api";
import type { FinRiskRequest, WorkflowRunSummary } from "../types";

const DEFAULT_REQUEST: FinRiskRequest = {
  ticker: "AAPL",
  company_name: "Apple",
  analysis_goal:
    "Identify macro, policy and supply-chain risks that changed recently.",
  time_horizon: "6-12 months",
  sources: ["filing", "web", "graph"],
  max_browser_steps: 5,
  demo_mode: true,
  cached_mode: false,
};

interface Props {
  onStarted: (summary: WorkflowRunSummary, request: FinRiskRequest) => void;
  busy: boolean;
}

const SOURCES = ["filing", "web", "transcript", "graph"] as const;

export function WorkflowLauncher({ onStarted, busy }: Props) {
  const [request, setRequest] = useState<FinRiskRequest>(DEFAULT_REQUEST);
  const [error, setError] = useState<string | null>(null);

  const update = <K extends keyof FinRiskRequest>(
    key: K,
    value: FinRiskRequest[K],
  ) => {
    setRequest((prev) => ({ ...prev, [key]: value }));
  };

  const toggleSource = (src: (typeof SOURCES)[number]) => {
    const current = request.sources || [];
    const next = current.includes(src)
      ? current.filter((s) => s !== src)
      : [...current, src];
    update("sources", next);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const summary = await api.startWorkflow(request);
      onStarted(summary, request);
    } catch (err) {
      const msg =
        err instanceof FinRiskApiError
          ? `API ${err.status}: ${JSON.stringify(err.body)}`
          : (err as Error).message;
      setError(msg);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2>Workflow Launcher</h2>
      <div className="row">
        <label htmlFor="ticker">Ticker</label>
        <input
          id="ticker"
          data-testid="ticker-input"
          value={request.ticker}
          onChange={(e) => update("ticker", e.target.value.toUpperCase())}
          required
        />
      </div>
      <div className="row">
        <label htmlFor="company">Company (opt.)</label>
        <input
          id="company"
          value={request.company_name ?? ""}
          onChange={(e) => update("company_name", e.target.value || null)}
        />
      </div>
      <div className="row">
        <label htmlFor="goal">Analysis goal</label>
        <textarea
          id="goal"
          data-testid="goal-input"
          value={request.analysis_goal}
          onChange={(e) => update("analysis_goal", e.target.value)}
          required
        />
      </div>
      <div className="row">
        <label htmlFor="horizon">Time horizon</label>
        <input
          id="horizon"
          value={request.time_horizon ?? ""}
          onChange={(e) => update("time_horizon", e.target.value)}
        />
      </div>
      <div className="row">
        <label>Sources</label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {SOURCES.map((src) => {
            const enabled = request.sources?.includes(src) ?? false;
            return (
              <label
                key={src}
                className="row-checkbox"
                style={{ margin: 0, cursor: "pointer" }}
              >
                <input
                  type="checkbox"
                  data-testid={`source-${src}`}
                  checked={enabled}
                  onChange={() => toggleSource(src)}
                />
                {src}
              </label>
            );
          })}
        </div>
      </div>
      <div className="row-checkbox">
        <input
          type="checkbox"
          id="demo-mode"
          data-testid="demo-mode"
          checked={request.demo_mode ?? false}
          onChange={(e) => update("demo_mode", e.target.checked)}
        />
        <label htmlFor="demo-mode">Demo mode (offline cached fixture)</label>
      </div>
      <div className="row-checkbox">
        <input
          type="checkbox"
          id="cached-mode"
          checked={request.cached_mode ?? false}
          onChange={(e) => update("cached_mode", e.target.checked)}
        />
        <label htmlFor="cached-mode">Cached mode (use cache when available)</label>
      </div>
      {error ? <div className="error-banner" data-testid="launcher-error">{error}</div> : null}
      <button
        type="submit"
        className="primary"
        disabled={busy}
        data-testid="run-button"
      >
        {busy ? "Working..." : "Run Risk Workflow"}
      </button>
    </form>
  );
}
