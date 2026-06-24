import { useEffect, useRef, useState } from "react";
import { AgentTimeline } from "./components/AgentTimeline";
import { ClaimEvidenceMatrix } from "./components/ClaimEvidenceMatrix";
import { EvaluationPanel } from "./components/EvaluationPanel";
import { EvaluationTab } from "./components/EvaluationTab";
import { EvidenceGraph } from "./components/EvidenceGraph";
import { RiskReport } from "./components/RiskReport";
import { RiskScoreBreakdown } from "./components/RiskScoreBreakdown";
import { WorkflowLauncher } from "./components/WorkflowLauncher";
import { api, FinRiskApiError } from "./api";
import type {
  FinRiskRequest,
  WorkflowEvaluationResponse,
  WorkflowGraphResponse,
  WorkflowReportResponse,
  WorkflowRunSummary,
  WorkflowStatusResponse,
} from "./types";

const POLL_INTERVAL_MS = 1500;

export function App() {
  const [, setRequest] = useState<FinRiskRequest | null>(null);
  const [summary, setSummary] = useState<WorkflowRunSummary | null>(null);
  const [status, setStatus] = useState<WorkflowStatusResponse | null>(null);
  const [report, setReport] = useState<WorkflowReportResponse | null>(null);
  const [graph, setGraph] = useState<WorkflowGraphResponse | null>(null);
  const [evaluation, setEvaluation] = useState<WorkflowEvaluationResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const pollRef = useRef<number | null>(null);

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setPolling(false);
  };

  const fetchStatusAndReport = async (runId: string) => {
    try {
      const next = await api.getStatus(runId);
      setStatus(next);
      if (
        next.status === "completed" ||
        next.status === "failed" ||
        next.status === "needs_review"
      ) {
        try {
          const r = await api.getReport(runId);
          setReport(r);
        } catch (err) {
          if (!(err instanceof FinRiskApiError)) {
            setError((err as Error).message);
          }
        }
        try {
          const g = await api.getGraph(runId);
          setGraph(g);
        } catch (err) {
          if (!(err instanceof FinRiskApiError)) {
            setError((err as Error).message);
          }
        }
        try {
          const e = await api.getEvaluation(runId);
          setEvaluation(e);
        } catch (err) {
          if (!(err instanceof FinRiskApiError)) {
            setError((err as Error).message);
          }
        }
        stopPolling();
      }
    } catch (err) {
      setError((err as Error).message);
      stopPolling();
    }
  };

  const startPolling = (runId: string) => {
    stopPolling();
    setPolling(true);
    void fetchStatusAndReport(runId);
    pollRef.current = window.setInterval(() => {
      void fetchStatusAndReport(runId);
    }, POLL_INTERVAL_MS);
  };

  useEffect(() => {
    return () => stopPolling();
  }, []);

  const handleStarted = (
    newSummary: WorkflowRunSummary,
    newRequest: FinRiskRequest,
  ) => {
    setError(null);
    setReport(null);
    setStatus(null);
    setGraph(null);
    setEvaluation(null);
    setSummary(newSummary);
    setRequest(newRequest);
    startPolling(newSummary.run_id);
  };

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>FinRisk Agent Studio</h1>
          <div className="subtitle">
            An AI-native financial risk intelligence workflow
          </div>
        </div>
        {summary ? (
          <div className="run-badge" data-testid="run-badge">
            {polling ? "● " : ""}
            {summary.run_id}
          </div>
        ) : null}
      </header>
      <div className="app-body">
        <aside className="app-side">
          <div className="section">
            <WorkflowLauncher
              onStarted={handleStarted}
              busy={polling}
            />
          </div>
        </aside>
        <main className="app-main">
          {error ? <div className="error-banner" data-testid="app-error">{error}</div> : null}
          {!summary ? (
            <div className="section empty-state" data-testid="empty-state">
              <p>
                Configure a workflow on the left and press <strong>Run Risk Workflow</strong>{" "}
                to see the timeline, report, evidence graph, and v16 evaluation
                populate here.
              </p>
              <p className="muted" style={{ fontSize: 12 }}>
                Default inputs target Apple (AAPL) in demo mode. Demo mode runs
                entirely offline using a cached fixture — no SEC, no GPU, no
                external network.
              </p>
            </div>
          ) : null}
          {summary ? <AgentTimeline status={status} /> : null}
          {summary ? (
            <EvaluationPanel
              evaluation={status?.evaluation ?? report?.evaluation ?? null}
            />
          ) : null}
          {summary ? (
            <EvaluationTab evaluation={evaluation} />
          ) : null}
          {summary ? (
            <RiskReport report={report?.report ?? null} />
          ) : null}
          {summary ? (
            <RiskScoreBreakdown
              scores={report?.report?.risk_scores ?? []}
            />
          ) : null}
          {summary ? (
            <ClaimEvidenceMatrix claims={[]} />
          ) : null}
          {summary ? (
            <EvidenceGraph
              report={report?.report ?? null}
              companyName={status?.company?.company_name ?? null}
              v16Paths={graph?.paths ?? null}
            />
          ) : null}
        </main>
      </div>
    </div>
  );
}

export default App;
