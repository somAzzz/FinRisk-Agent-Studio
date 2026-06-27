import { useCallback, useEffect, useRef, useState } from "react";
import { Boxes, GitBranch, Radar } from "lucide-react";
import { AgentTimeline } from "./components/AgentTimeline";
import {
  AgentProcessMonitor,
  type ProcessMonitorSnapshot,
  type ProcessNodeStatus,
} from "./components/AgentProcessMonitor";
import { ClaimEvidenceMatrix } from "./components/ClaimEvidenceMatrix";
import { EvaluationPanel } from "./components/EvaluationPanel";
import { EvaluationTab } from "./components/EvaluationTab";
import { EvidenceGraph } from "./components/EvidenceGraph";
import { LLMAgentRunPanel } from "./components/LLMAgentRunPanel";
import { RiskReport } from "./components/RiskReport";
import { RiskScoreBreakdown } from "./components/RiskScoreBreakdown";
import {
  RunHistoryPanel,
  type RunHistoryItem,
} from "./components/RunHistoryPanel";
import { SupplyChainExplorer } from "./components/SupplyChainExplorer";
import { WorkflowLauncher } from "./components/WorkflowLauncher";
import { api, FinRiskApiError } from "./api";
import type {
  AgentRunTimelineResponse,
  FinRiskRequest,
  WorkflowEvaluationResponse,
  WorkflowGraphResponse,
  WorkflowReportResponse,
  WorkflowRunSummary,
  WorkflowStatusResponse,
  WorkflowTraceEvent,
} from "./types";
import type { SupplyChainStatusResponseWire } from "./supply-chain-types";

const POLL_INTERVAL_MS = 1500;

type AppView = "finrisk" | "supply-chain" | "agent-runs";

const FINRISK_STEPS = [
  "company_resolver",
  "filing_risk_extractor",
  "market_explorer",
  "evidence_normalizer",
  "risk_scorer",
  "graph_reasoner",
  "report_generator",
  "evaluator",
];

const DEFAULT_MONITOR: ProcessMonitorSnapshot = {
  title: "No active run",
  status: "idle",
  nodes: [
    {
      id: "idle",
      label: "Waiting",
      status: "queued",
      log: "Start a workflow, agent run, or supply-chain exploration to stream progress here.",
    },
  ],
};

function emptyMonitor(title: string): ProcessMonitorSnapshot {
  return {
    ...DEFAULT_MONITOR,
    title,
    nodes: DEFAULT_MONITOR.nodes.map((node) => ({ ...node })),
  };
}

function initialProcessMonitors(): Record<AppView, ProcessMonitorSnapshot> {
  return {
    finrisk: emptyMonitor("Risk Intelligence"),
    "supply-chain": emptyMonitor("Product Supply Chain"),
    "agent-runs": emptyMonitor("LLM Agent Run"),
  };
}

function normalizeMonitorStatus(status: string | null | undefined): ProcessNodeStatus {
  if (status === "completed") return "completed";
  if (status === "running") return "running";
  if (status === "failed") return "failed";
  if (status === "needs_review") return "needs_review";
  if (status === "queued" || status === "created") return "queued";
  return "skipped";
}

function prettyStepName(value: string): string {
  return value.split("_").join(" ");
}

function finriskSnapshot(status: WorkflowStatusResponse | null): ProcessMonitorSnapshot {
  if (!status) return DEFAULT_MONITOR;
  const eventByName = new Map(status.trace.map((event) => [event.step_name, event]));
  return {
    title: "Risk Intelligence",
    runId: status.run_id,
    status: status.status,
    nodes: FINRISK_STEPS.map((stepName) => {
      const event = eventByName.get(stepName);
      return {
        id: stepName,
        label: prettyStepName(stepName),
        status: event?.status ?? "skipped",
        log: formatWorkflowLog(event, status.current_step),
        meta: event?.completed_at
          ? `completed ${new Date(event.completed_at).toLocaleTimeString()}`
          : event?.started_at
            ? `started ${new Date(event.started_at).toLocaleTimeString()}`
            : undefined,
      };
    }),
  };
}

function formatWorkflowLog(
  event: WorkflowTraceEvent | undefined,
  currentStep: string | null | undefined,
): string {
  if (!event) return "This step has not emitted a trace event yet.";
  if (event.error) return event.error;
  if (event.status === "running") {
    return currentStep
      ? `Running ${currentStep}; waiting for the next trace update.`
      : "Step is running; waiting for the next trace update.";
  }
  return `Step ${event.status}.`;
}

function agentRunSnapshot(
  timeline: AgentRunTimelineResponse | null,
): ProcessMonitorSnapshot {
  if (!timeline) return DEFAULT_MONITOR;
  const nodes =
    timeline.subgoals.length > 0
      ? timeline.subgoals.map((subgoal) => {
          const relatedTools = timeline.tool_events.filter(
            (event) => event.round_id || event.tool_name,
          );
          const toolSummary =
            relatedTools.length > 0
              ? `${relatedTools.length} tool event(s), ${timeline.evidence_candidates.length} evidence candidate(s).`
              : "No tool events have been recorded for this agent run yet.";
          return {
            id: subgoal.subgoal_id,
            label: prettyStepName(subgoal.tool_scope),
            status: normalizeMonitorStatus(subgoal.status),
            log: `${subgoal.objective} ${toolSummary}`,
            meta: subgoal.required_evidence_types.length
              ? `requires ${subgoal.required_evidence_types.join(", ")}`
              : undefined,
          };
        })
      : [
          {
            id: "agent-planner",
            label: "planner",
            status: normalizeMonitorStatus(timeline.status),
            log:
              timeline.decisions[timeline.decisions.length - 1]?.rationale ??
              "Planner has not emitted a decision yet.",
          },
        ];
  return {
    title: "LLM Agent Run",
    runId: timeline.run_id,
    status: timeline.status,
    nodes,
  };
}

function supplyChainSnapshot(
  status: SupplyChainStatusResponseWire | null,
): ProcessMonitorSnapshot {
  if (!status) return DEFAULT_MONITOR;
  const traceNodes = status.trace.length
    ? status.trace.map((event, index) => {
        const stepName = String(event.step_name ?? `step ${index + 1}`);
        const eventStatus = String(event.status ?? status.status);
        const message =
          String(event.message ?? event.error ?? "") ||
          `nodes ${status.node_count}, links ${status.link_count}, evidence ${status.evidence_count}`;
        return {
          id: `${stepName}-${index}`,
          label: prettyStepName(stepName),
          status: normalizeMonitorStatus(eventStatus),
          log: message,
          meta: status.current_step === stepName ? "current step" : undefined,
        };
      })
    : [
        {
          id: "supply-chain-run",
          label: status.current_step ? prettyStepName(status.current_step) : "supply graph",
          status: normalizeMonitorStatus(status.status),
          log: `nodes ${status.node_count}, links ${status.link_count}, evidence ${status.evidence_count}`,
        },
      ];
  return {
    title: "Product Supply Chain",
    runId: status.run_id,
    status: status.status,
    nodes: traceNodes,
  };
}

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
  const [processMonitors, setProcessMonitors] =
    useState<Record<AppView, ProcessMonitorSnapshot>>(initialProcessMonitors);
  const [historyItems, setHistoryItems] = useState<RunHistoryItem[]>([]);
  const [selectedHistoryRunId, setSelectedHistoryRunId] = useState<string | null>(null);
  const [selectedAgentRunId, setSelectedAgentRunId] = useState<string | null>(null);
  const [selectedSupplyChainRunId, setSelectedSupplyChainRunId] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<AppView>("finrisk");
  const pollRef = useRef<number | null>(null);

  const setViewMonitor = useCallback((view: AppView, snapshot: ProcessMonitorSnapshot) => {
    setProcessMonitors((current) => ({
      ...current,
      [view]: snapshot,
    }));
  }, []);

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setPolling(false);
  };

  const refreshHistory = async () => {
    const [workflows, agents, supplyChains] = await Promise.all([
      api.listWorkflows(10).catch(() => []),
      api.listAgentRuns(10).catch(() => []),
      api.listSupplyChains(10).catch(() => []),
    ]);
    setHistoryItems([
      ...agents.map((item): RunHistoryItem => ({
        kind: "agent-runs",
        runId: item.run_id,
        status: item.status,
        title: "LLM Agent Run",
      })),
      ...supplyChains.map((item): RunHistoryItem => ({
        kind: "supply-chain",
        runId: item.run_id,
        status: item.status,
        title: "Product Supply Chain",
      })),
      ...workflows.map((item): RunHistoryItem => ({
        kind: "finrisk",
        runId: item.run_id,
        status: item.status,
        title: "Risk Intelligence",
        detail: item.current_step,
      })),
    ].slice(0, 20));
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

  useEffect(() => {
    void refreshHistory();
    const id = window.setInterval(() => {
      void refreshHistory();
    }, 10000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (status) {
      setViewMonitor("finrisk", finriskSnapshot(status));
    }
  }, [setViewMonitor, status]);

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
    setSelectedHistoryRunId(newSummary.run_id);
    setRequest(newRequest);
    setViewMonitor("finrisk", {
      title: "Risk Intelligence",
      runId: newSummary.run_id,
      status: newSummary.status,
      nodes: FINRISK_STEPS.map((stepName, index) => ({
        id: stepName,
        label: prettyStepName(stepName),
        status: index === 0 ? "queued" : "skipped",
        log: "Workflow has been queued; waiting for the first backend trace event.",
      })),
    });
    startPolling(newSummary.run_id);
    void refreshHistory();
  };

  const loadFinriskRun = async (runId: string) => {
    stopPolling();
    setError(null);
    const next = await api.getStatus(runId);
    setSummary({
      run_id: next.run_id,
      status: next.status,
      current_step: next.current_step,
      started_at: next.trace[0]?.started_at ?? new Date().toISOString(),
      completed_at: next.completed_at,
      report_url: `/workflows/${next.run_id}/report`,
    });
    setStatus(next);
    setViewMonitor("finrisk", finriskSnapshot(next));
    if (
      next.status === "completed" ||
      next.status === "failed" ||
      next.status === "needs_review"
    ) {
      try {
        setReport(await api.getReport(runId));
      } catch (err) {
        if (!(err instanceof FinRiskApiError)) setError((err as Error).message);
      }
      try {
        setGraph(await api.getGraph(runId));
      } catch (err) {
        if (!(err instanceof FinRiskApiError)) setError((err as Error).message);
      }
      try {
        setEvaluation(await api.getEvaluation(runId));
      } catch (err) {
        if (!(err instanceof FinRiskApiError)) setError((err as Error).message);
      }
      setPolling(false);
    } else {
      startPolling(runId);
    }
  };

  const handleSelectHistory = (item: RunHistoryItem) => {
    setSelectedHistoryRunId(item.runId);
    if (item.kind === "finrisk") {
      setActiveView("finrisk");
      void loadFinriskRun(item.runId);
      return;
    }
    if (item.kind === "agent-runs") {
      setActiveView("agent-runs");
      setSelectedAgentRunId(item.runId);
      return;
    }
    setActiveView("supply-chain");
    setSelectedSupplyChainRunId(item.runId);
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            FR
          </div>
          <div>
          <h1>FinRisk Agent Studio</h1>
          <div className="subtitle">
            Risk orchestration console
          </div>
          </div>
        </div>
        <div className="ops-strip" aria-label="Runtime status">
          <span>Graph online</span>
          <span>LLM routed</span>
          <span>Evidence gated</span>
        </div>
        {summary ? (
          <div className="run-badge" data-testid="run-badge">
            {polling ? "live " : ""}
            {summary.run_id}
          </div>
        ) : null}
      </header>
      <nav className="app-tabs" aria-label="Application views">
        <button
          type="button"
          className={activeView === "finrisk" ? "active" : ""}
          onClick={() => setActiveView("finrisk")}
          data-testid="tab-finrisk"
        >
          <Radar size={15} />
          Risk Intelligence
        </button>
        <button
          type="button"
          className={activeView === "supply-chain" ? "active" : ""}
          onClick={() => setActiveView("supply-chain")}
          data-testid="tab-supply-chain"
        >
          <GitBranch size={15} />
          Product Supply Chain
        </button>
        <button
          type="button"
          className={activeView === "agent-runs" ? "active" : ""}
          onClick={() => setActiveView("agent-runs")}
          data-testid="tab-agent-runs"
        >
          <Boxes size={15} />
          LLM Agent Runs
        </button>
      </nav>
      <main
        className={`app-main agent-runs-view view-panel ${
          activeView === "agent-runs" ? "active" : ""
        }`}
        aria-hidden={activeView !== "agent-runs"}
      >
        <LLMAgentRunPanel
          selectedRunId={selectedAgentRunId}
          onProgress={(timeline) => {
            if (timeline) setSelectedHistoryRunId(timeline.run_id);
            setViewMonitor("agent-runs", agentRunSnapshot(timeline));
          }}
        />
      </main>
      <main
        className={`app-main supply-chain-view view-panel ${
          activeView === "supply-chain" ? "active" : ""
        }`}
        aria-hidden={activeView !== "supply-chain"}
      >
        <SupplyChainExplorer
          selectedRunId={selectedSupplyChainRunId}
          onProgress={(nextStatus) => {
            if (nextStatus) setSelectedHistoryRunId(nextStatus.run_id);
            setViewMonitor("supply-chain", supplyChainSnapshot(nextStatus));
          }}
        />
      </main>
      <div
        className={`app-body view-panel ${
          activeView === "finrisk" ? "active" : ""
        }`}
        aria-hidden={activeView !== "finrisk"}
      >
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
            <RiskReport
              report={report?.report_v16 ? null : report?.report ?? null}
              reportV16={report?.report_v16 ?? null}
            />
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
      <RunHistoryPanel
        items={historyItems}
        selectedRunId={selectedHistoryRunId}
        onSelect={handleSelectHistory}
        onRefresh={() => void refreshHistory()}
      />
      <AgentProcessMonitor snapshot={processMonitors[activeView]} />
    </div>
  );
}

export default App;
