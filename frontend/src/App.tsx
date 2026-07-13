import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  BookOpen,
  Building2,
  ChevronDown,
  CircleGauge,
  CircleMinus,
  FileSearch,
  Home,
  Menu,
  Play,
  RefreshCw,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import { FaApple } from "react-icons/fa";
import { AgentTimeline } from "./components/AgentTimeline";
import {
  type ProcessMonitorSnapshot,
  type ProcessNodeStatus,
} from "./components/AgentProcessMonitor";
const CompanyRisksPage = lazy(() => import("./components/CompanyRisksPage").then((module) => ({ default: module.CompanyRisksPage })));
const CompanyEvidencePage = lazy(() => import("./components/CompanyEvidencePage").then((module) => ({ default: module.CompanyEvidencePage })));
import { EvaluationPanel } from "./components/EvaluationPanel";
import { EvaluationTab } from "./components/EvaluationTab";
import { EvidenceGraph } from "./components/EvidenceGraph";
const FinancialTrendPanel = lazy(() => import("./components/FinancialTrendPanel").then((module) => ({ default: module.FinancialTrendPanel })));
const LLMAgentRunPanel = lazy(() => import("./components/LLMAgentRunPanel").then((module) => ({ default: module.LLMAgentRunPanel })));
const ManagementComparisonPanel = lazy(() => import("./components/ManagementComparisonPanel").then((module) => ({ default: module.ManagementComparisonPanel })));
const ResearchDecisionBrief = lazy(() => import("./components/ResearchDecisionBrief").then((module) => ({ default: module.ResearchDecisionBrief })));
import type { OverviewRiskRow } from "./components/ResearchDecisionBrief";
const ResearchJournalPanel = lazy(() => import("./components/ResearchJournalPanel").then((module) => ({ default: module.ResearchJournalPanel })));
import { RiskScoreBreakdown } from "./components/RiskScoreBreakdown";
const ScenarioValuationPanel = lazy(() => import("./components/ScenarioValuationPanel").then((module) => ({ default: module.ScenarioValuationPanel })));
import type { RunHistoryItem } from "./components/RunHistoryPanel";
const SupplyChainExplorer = lazy(() => import("./components/SupplyChainExplorer").then((module) => ({ default: module.SupplyChainExplorer })));
import { TodayDashboard } from "./components/TodayDashboard";
import { WorkflowLauncher } from "./components/WorkflowLauncher";
import { api, describeApiError } from "./api";
import {
  isStaticDemoMode,
  staticDemoEvaluation,
  staticDemoGraph,
  staticDemoReport,
  staticDemoStatus,
  staticDemoSummary,
} from "./staticDemo";
import type {
  AgentRunTimelineResponse,
  FinRiskRequest,
  FinancialSnapshot,
  WorkflowEvaluationResponse,
  WorkflowGraphResponse,
  WorkflowReportResponse,
  WorkflowRunSummary,
  WorkflowStatusResponse,
  WorkflowTraceEvent,
} from "./types";
import type { SupplyChainStatusResponseWire } from "./supply-chain-types";
import {
  staticDemoFinancials,
  staticEvidenceBreakdown,
  staticManagementComparison,
  staticOverviewRisks,
  staticSupplyChain,
} from "./productDemo";

const POLL_INTERVAL_MS = 1500;
const STATIC_DEMO_MODE = isStaticDemoMode();

type AppView = "finrisk" | "supply-chain" | "agent-runs" | "journal";
type ProductPage = "today" | "companies" | "runs" | "journal";
type CompanySection =
  | "overview"
  | "risks"
  | "financials"
  | "valuation"
  | "management"
  | "supply-chain"
  | "evidence";

interface ProductRoute {
  page: ProductPage;
  section: CompanySection;
}

const COMPANY_SECTIONS = new Set<CompanySection>([
  "overview",
  "risks",
  "financials",
  "valuation",
  "management",
  "supply-chain",
  "evidence",
]);

function routeFromLocation(): ProductRoute {
  if (typeof window === "undefined") return { page: "today", section: "overview" };
  const route = window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (route[0] === "companies") {
    const requestedSection = route[2] as CompanySection | undefined;
    return {
      page: "companies",
      section: requestedSection && COMPANY_SECTIONS.has(requestedSection) ? requestedSection : "overview",
    };
  }
  if (route[0] === "runs") return { page: "runs", section: "overview" };
  if (route[0] === "journal") return { page: "journal", section: "overview" };
  if (route[0] === "today") return { page: "today", section: "overview" };
  return STATIC_DEMO_MODE
    ? { page: "companies", section: "overview" }
    : { page: "today", section: "overview" };
}

function routeHash(route: ProductRoute): string {
  if (route.page === "companies") return `#/companies/AAPL/${route.section}`;
  return `#/${route.page}`;
}

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
    journal: emptyMonitor("Research Journal"),
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
  const [summary, setSummary] = useState<WorkflowRunSummary | null>(
    STATIC_DEMO_MODE ? staticDemoSummary : null,
  );
  const [status, setStatus] = useState<WorkflowStatusResponse | null>(
    STATIC_DEMO_MODE ? staticDemoStatus : null,
  );
  const [report, setReport] = useState<WorkflowReportResponse | null>(
    STATIC_DEMO_MODE ? staticDemoReport : null,
  );
  const [graph, setGraph] = useState<WorkflowGraphResponse | null>(
    STATIC_DEMO_MODE ? staticDemoGraph : null,
  );
  const [evaluation, setEvaluation] = useState<WorkflowEvaluationResponse | null>(
    STATIC_DEMO_MODE ? staticDemoEvaluation : null,
  );
  const [financials, setFinancials] = useState<FinancialSnapshot | null>(
    STATIC_DEMO_MODE ? staticDemoFinancials : null,
  );
  const [financialsLoading, setFinancialsLoading] = useState(false);
  const [financialsError, setFinancialsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const [processMonitors, setProcessMonitors] =
    useState<Record<AppView, ProcessMonitorSnapshot>>(initialProcessMonitors);
  const [historyItems, setHistoryItems] = useState<RunHistoryItem[]>(
    STATIC_DEMO_MODE
      ? [
          {
            kind: "agent-runs",
            runId: "agent-aapl-fixture",
            status: "completed",
            title: "Supply-chain evidence review",
            detail: "1 item needs analyst judgment",
          },
          {
            kind: "finrisk",
            runId: staticDemoSummary.run_id,
            status: staticDemoSummary.status,
            title: "Risk Intelligence",
            detail: "GitHub Pages static demo",
          },
        ]
      : [],
  );
  const [selectedHistoryRunId, setSelectedHistoryRunId] = useState<string | null>(
    STATIC_DEMO_MODE ? "agent-aapl-fixture" : null,
  );
  const [selectedAgentRunId, setSelectedAgentRunId] = useState<string | null>(null);
  const [selectedSupplyChainRunId, setSelectedSupplyChainRunId] = useState<string | null>(null);
  const [route, setRoute] = useState<ProductRoute>(routeFromLocation);
  const [runPanelOpen, setRunPanelOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [serviceHealth, setServiceHealth] = useState<"checking" | "available" | "partial" | "fixture">(
    STATIC_DEMO_MODE ? "fixture" : "checking",
  );
  const pollRef = useRef<number | null>(null);
  const activeView: AppView =
    route.page === "runs"
      ? "agent-runs"
      : route.page === "journal"
        ? "journal"
        : route.page === "companies" && route.section === "supply-chain"
          ? "supply-chain"
          : "finrisk";

  const navigate = useCallback((next: ProductRoute) => {
    setRoute(next);
    setMobileNavOpen(false);
    window.history.pushState(null, "", routeHash(next));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

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
    if (STATIC_DEMO_MODE) return;
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

  const loadStaticDemo = () => {
    stopPolling();
    setError(null);
    setSummary(staticDemoSummary);
    setStatus(staticDemoStatus);
    setReport(staticDemoReport);
    setGraph(staticDemoGraph);
    setEvaluation(staticDemoEvaluation);
    setFinancials(staticDemoFinancials);
    setSelectedHistoryRunId(staticDemoSummary.run_id);
    setViewMonitor("finrisk", finriskSnapshot(staticDemoStatus));
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
        stopPolling();
        try {
          const r = await api.getReport(runId);
          setReport(r);
        } catch (err) {
          setError(describeApiError(err, "Risk report"));
        }
        try {
          const g = await api.getGraph(runId);
          setGraph(g);
        } catch (err) {
          setError(describeApiError(err, "Evidence graph"));
        }
        try {
          const e = await api.getEvaluation(runId);
          setEvaluation(e);
        } catch (err) {
          setError(describeApiError(err, "Workflow evaluation"));
        }
        if (!STATIC_DEMO_MODE && next.company?.ticker) {
          setFinancialsLoading(true);
          setFinancialsError(null);
          try {
            setFinancials(await api.getFinancialSnapshot(next.company.ticker));
          } catch (nextError) {
            setFinancials(null);
            setFinancialsError(describeApiError(nextError, "SEC financial history"));
          } finally {
            setFinancialsLoading(false);
          }
        }
      }
    } catch (err) {
      setError(describeApiError(err, "Workflow status"));
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
    if (!window.location.hash) {
      window.history.replaceState(null, "", routeHash(route));
    }
    const syncRoute = () => setRoute(routeFromLocation());
    window.addEventListener("hashchange", syncRoute);
    window.addEventListener("popstate", syncRoute);
    return () => {
      window.removeEventListener("hashchange", syncRoute);
      window.removeEventListener("popstate", syncRoute);
    };
  }, []);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [route.page, route.section]);

  useEffect(() => {
    if (STATIC_DEMO_MODE) {
      setServiceHealth("fixture");
      return;
    }
    setServiceHealth("checking");
    void api.health()
      .then(() => setServiceHealth("available"))
      .catch(() => setServiceHealth("partial"));
  }, []);

  useEffect(() => {
    if (!runPanelOpen && !activityOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setRunPanelOpen(false);
      setActivityOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [activityOpen, runPanelOpen]);

  useEffect(() => {
    if (STATIC_DEMO_MODE) {
      setViewMonitor("finrisk", finriskSnapshot(staticDemoStatus));
      return undefined;
    }
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
    setFinancials(null);
    setFinancialsError(null);
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
    setRunPanelOpen(false);
    navigate({ page: "companies", section: "overview" });
  };

  const loadFinriskRun = async (runId: string) => {
    stopPolling();
    setError(null);
    setFinancials(null);
    setFinancialsError(null);
    setFinancialsLoading(false);
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
        setError(describeApiError(err, "Risk report"));
      }
      try {
        setGraph(await api.getGraph(runId));
      } catch (err) {
        setError(describeApiError(err, "Evidence graph"));
      }
      try {
        setEvaluation(await api.getEvaluation(runId));
      } catch (err) {
        setError(describeApiError(err, "Workflow evaluation"));
      }
      if (next.company?.ticker) {
        setFinancialsLoading(true);
        setFinancialsError(null);
        try {
          setFinancials(await api.getFinancialSnapshot(next.company.ticker));
        } catch (nextError) {
          setFinancials(null);
          setFinancialsError(describeApiError(nextError, "SEC financial history"));
        } finally {
          setFinancialsLoading(false);
        }
      }
      setPolling(false);
    } else {
      startPolling(runId);
    }
  };

  const handleSelectHistory = (item: RunHistoryItem) => {
    setSelectedHistoryRunId(item.runId);
    if (item.kind === "finrisk") {
      navigate({ page: "companies", section: "overview" });
      if (STATIC_DEMO_MODE) {
        loadStaticDemo();
        return;
      }
      void loadFinriskRun(item.runId);
      return;
    }
    if (item.kind === "agent-runs") {
      navigate({ page: "runs", section: "overview" });
      setSelectedAgentRunId(item.runId);
      return;
    }
    navigate({ page: "companies", section: "supply-chain" });
    setSelectedSupplyChainRunId(item.runId);
  };

  const companyName = status?.company?.company_name ?? "Apple Inc.";
  const companyTicker = status?.company?.ticker ?? "AAPL";
  const lastUpdated = summary?.completed_at ?? status?.completed_at ?? summary?.started_at ?? null;
  const activeMonitor = processMonitors[activeView];
  const healthLabel =
    serviceHealth === "available"
      ? "Available"
      : serviceHealth === "fixture"
        ? "Partially available"
        : serviceHealth === "checking"
          ? "Checking"
          : "Partially available";
  const companyTabs: Array<{ id: CompanySection; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "risks", label: "Risks" },
    { id: "financials", label: "Financials" },
    { id: "valuation", label: "Valuation" },
    { id: "management", label: "Management" },
    { id: "supply-chain", label: "Supply Chain" },
    { id: "evidence", label: "Evidence" },
  ];
  const companyRiskRows: OverviewRiskRow[] = STATIC_DEMO_MODE
    ? staticOverviewRisks
    : (report?.report_v16?.top_risks ?? []).map((risk) => ({
        id: risk.risk_id,
        title: risk.title.split("_").map((part) => part ? `${part[0].toUpperCase()}${part.slice(1)}` : part).join(" "),
        summary: risk.summary,
        score: risk.final_score,
        trend: [risk.final_score - 1.8, risk.final_score - 1.2, risk.final_score - 1.5, risk.final_score - 0.7, risk.final_score - 0.4, risk.final_score - 0.2, risk.final_score],
        change: 0,
        confidence: "Medium" as const,
      }));

  return (
    <div className="product-app">
      <a className="skip-link" href="#main-content">Skip to current workspace</a>
      <aside className={`product-sidebar ${mobileNavOpen ? "open" : ""}`}>
        <div className="product-brand">
          <div className="brand-mark" aria-hidden="true">FR</div>
          <div><strong>FinRisk</strong><span>Agent Studio</span></div>
          <button className="mobile-nav-toggle" type="button" onClick={() => setMobileNavOpen((value) => !value)} aria-label={mobileNavOpen ? "Close navigation" : "Open navigation"} aria-expanded={mobileNavOpen}>
            {mobileNavOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        <nav className="product-navigation" aria-label="Primary navigation">
          <button type="button" className={route.page === "today" ? "active" : ""} aria-current={route.page === "today" ? "page" : undefined} onClick={() => navigate({ page: "today", section: "overview" })}>
            <Home size={18} aria-hidden="true" /> Today
          </button>
          <button type="button" className={route.page === "companies" ? "active" : ""} aria-current={route.page === "companies" ? "page" : undefined} onClick={() => navigate({ page: "companies", section: "overview" })} data-testid="tab-finrisk">
            <Building2 size={18} aria-hidden="true" /> Companies
          </button>
          <button type="button" className={route.page === "runs" ? "active" : ""} aria-current={route.page === "runs" ? "page" : undefined} onClick={() => navigate({ page: "runs", section: "overview" })} data-testid="tab-agent-runs">
            <Activity size={18} aria-hidden="true" /> Research Runs
          </button>
          <button type="button" className={route.page === "journal" ? "active" : ""} aria-current={route.page === "journal" ? "page" : undefined} onClick={() => navigate({ page: "journal", section: "overview" })} data-testid="tab-journal">
            <BookOpen size={18} aria-hidden="true" /> Journal
          </button>
        </nav>
        <div className="sidebar-footer">
          <button type="button" onClick={() => setActivityOpen(true)}>
            <CircleGauge size={18} aria-hidden="true" /> Activity
            {polling ? <span className="live-dot" aria-label="Research run in progress" /> : null}
          </button>
          <button type="button" onClick={() => setRunPanelOpen(true)}>
            <Settings size={18} aria-hidden="true" /> Runtime settings
          </button>
          <div className="analyst-profile"><span>AA</span><div><strong>Analyst</strong><small>Research team</small></div></div>
        </div>
      </aside>

      <div className="product-content">
        {route.page === "companies" ? (
          <>
            <header className="company-header">
              <div className="company-identity">
                <div className="company-icon"><FaApple size={38} aria-hidden="true" /></div>
                <div>
                  <div className="company-title-row"><h1>{companyName}</h1><span>{companyTicker}</span></div>
                  <p>Technology Hardware, Storage &amp; Peripherals · Nasdaq</p>
                  <small>Last updated: {STATIC_DEMO_MODE ? "July 12, 2026 10:32 AM ET" : lastUpdated ? new Date(lastUpdated).toLocaleString() : "No completed update"}</small>
                </div>
              </div>
              <button className={`data-health ${serviceHealth}`} type="button" onClick={() => setActivityOpen(true)}>
                {serviceHealth === "partial" || serviceHealth === "fixture" ? <CircleMinus size={19} aria-hidden="true" /> : <ShieldCheck size={19} aria-hidden="true" />}
                <span><small>Data health</small><strong>{healthLabel}</strong></span>
                <ChevronDown size={16} aria-hidden="true" />
              </button>
              <button className="product-primary run-update" type="button" onClick={() => setRunPanelOpen(true)}>
                <RefreshCw size={17} aria-hidden="true" /> Run update
              </button>
            </header>
            <nav className="company-tabs" aria-label={`${companyName} workspace sections`}>
              {companyTabs.map((tab) => (
                <button type="button" key={tab.id} className={route.section === tab.id ? "active" : ""} aria-current={route.section === tab.id ? "page" : undefined} onClick={() => navigate({ page: "companies", section: tab.id })} data-testid={tab.id === "supply-chain" ? "tab-supply-chain" : undefined}>
                  {tab.label}
                </button>
              ))}
            </nav>
          </>
        ) : null}

        {error ? <div className="product-error" role="alert" data-testid="app-error"><span>{error}</span><button type="button" onClick={() => setError(null)} aria-label="Dismiss error"><X size={15} /></button></div> : null}

        <Suspense fallback={<main className="product-page route-loading" id="main-content"><span className="page-eyebrow">Loading workspace</span><h2>Preparing the latest research view…</h2></main>}>
        {route.page === "today" ? (
          <TodayDashboard historyItems={historyItems} hasCompanyBrief={Boolean(report?.report_v16)} onOpenCompany={() => navigate({ page: "companies", section: "overview" })} onOpenRuns={() => navigate({ page: "runs", section: "overview" })} onStartResearch={() => setRunPanelOpen(true)} />
        ) : null}

        {route.page === "companies" ? (
          <main className="company-page product-page" id="main-content" tabIndex={-1}>
            {!summary ? (
              <section className="company-empty" data-testid="empty-state">
                <FileSearch size={30} aria-hidden="true" />
                <div><h2>Establish the first company baseline</h2><p>Run an evidence-linked update to populate risks, financials, management signals and source quality.</p></div>
                <button className="product-primary" type="button" onClick={() => setRunPanelOpen(true)}>Run first update</button>
              </section>
            ) : null}
            {summary && route.section === "overview" ? (
              <>
                <ResearchDecisionBrief company={status?.company ?? null} report={report?.report_v16 ?? null} evaluation={status?.evaluation ?? report?.evaluation ?? null} onViewRisks={() => navigate({ page: "companies", section: "risks" })} onViewEvidence={() => navigate({ page: "companies", section: "evidence" })} displayRisks={STATIC_DEMO_MODE ? staticOverviewRisks : undefined} evidenceBreakdown={STATIC_DEMO_MODE ? staticEvidenceBreakdown : undefined} evidenceConfidenceScore={STATIC_DEMO_MODE ? 78 : undefined} evidenceItemCount={STATIC_DEMO_MODE ? 147 : undefined} recentEvidenceCount={STATIC_DEMO_MODE ? 84 : undefined} conflictingEvidenceCount={STATIC_DEMO_MODE ? 6 : undefined} />
                <details className="technical-trace">
                  <summary><span>Technical trace</span><small>{status?.trace.length ?? 0} workflow steps</small></summary>
                  <AgentTimeline status={status} />
                </details>
              </>
            ) : null}
            {summary && route.section === "risks" ? (
              <div className="subpage-stack"><header className="subpage-heading"><span className="page-eyebrow">Company analysis</span><h2>Risks</h2><p>Ranked claims, transmission channels and evidence-linked changes.</p></header><CompanyRisksPage report={report?.report_v16 ?? null} legacyReport={report?.report ?? null} risks={companyRiskRows} onReviewEvidence={() => navigate({ page: "companies", section: "evidence" })} />{report?.report?.risk_scores?.length ? <RiskScoreBreakdown scores={report.report.risk_scores} /> : null}</div>
            ) : null}
            {route.section === "financials" ? <div className="subpage-stack"><header className="subpage-heading"><span className="page-eyebrow">Standardized facts</span><h2>Financials</h2><p>Point-in-time SEC metrics with lineage and change checks.</p></header><FinancialTrendPanel snapshot={financials} loading={financialsLoading} error={financialsError ?? (!financials && !STATIC_DEMO_MODE ? "Financial history has not been loaded for this company." : null)} />{!financials && STATIC_DEMO_MODE ? <div className="directed-empty"><BarChart3 size={24} /><div><strong>Financials are not included in the static fixture.</strong><p>Connect the API to load standardized SEC facts.</p></div></div> : null}</div> : null}
            {route.section === "valuation" ? <div className="subpage-stack"><header className="subpage-heading"><span className="page-eyebrow">Assumption-led</span><h2>Valuation</h2><p>Scenarios remain separate from observed evidence and preserve every assumption.</p></header><ScenarioValuationPanel snapshot={financials} staticMode={STATIC_DEMO_MODE} /></div> : null}
            {route.section === "management" ? <div className="subpage-stack"><header className="subpage-heading"><span className="page-eyebrow">Transcript comparison</span><h2>Management</h2><p>Compare topic shifts and claims across earnings calls.</p></header><ManagementComparisonPanel ticker={status?.company?.ticker ?? companyTicker} demoResult={STATIC_DEMO_MODE ? staticManagementComparison : undefined} /></div> : null}
            {route.section === "supply-chain" ? <SupplyChainExplorer initialCompany={companyName} initialProduct="iPhone" initialPayload={STATIC_DEMO_MODE ? staticSupplyChain : undefined} selectedRunId={selectedSupplyChainRunId} onProgress={(nextStatus) => { if (nextStatus) setSelectedHistoryRunId(nextStatus.run_id); setViewMonitor("supply-chain", supplyChainSnapshot(nextStatus)); }} /> : null}
            {summary && route.section === "evidence" ? (
              <div className="subpage-stack"><header className="subpage-heading"><span className="page-eyebrow">Grounding and quality</span><h2>Evidence</h2><p>Review claim coverage, source quality, guardrails and graph paths in one place.</p></header><CompanyEvidencePage evaluation={evaluation ?? status?.evaluation ?? report?.evaluation ?? null} claims={(report?.report_v16?.evidence_vs_inference ?? []).map((claim) => ({ ...claim, grounding: claim.supporting_evidence_ids.length ? "grounded" : "unsupported", status: claim.supporting_evidence_ids.length ? "pass" : "needs_review", recommendation: claim.supporting_evidence_ids.length ? null : "Link primary evidence before relying on this claim." }))} staticMode={STATIC_DEMO_MODE} graphContent={<><EvidenceGraph report={report?.report ?? null} companyName={companyName} v16Paths={graph?.paths ?? null} />{evaluation ? <EvaluationTab evaluation={evaluation} runId={summary.run_id} /> : <EvaluationPanel evaluation={status?.evaluation ?? report?.evaluation ?? null} />}</>} /></div>
            ) : null}
          </main>
        ) : null}

        {route.page === "runs" ? (
          <main className="runs-page product-page" id="main-content" tabIndex={-1}>
            <header className="page-heading"><div><span className="page-eyebrow">Execution review</span><h1>Research runs</h1><p>Decide whether each run is trustworthy, then resolve the evidence that needs human judgment.</p></div><button className="product-primary" type="button" onClick={() => setRunPanelOpen(true)}><Play size={16} /> New company update</button></header>
            <div className="runs-layout">
              <section className="inline-history"><header className="section-heading-row"><div><span className="page-eyebrow">Latest first</span><h2>Run history</h2></div><button className="text-action" type="button" onClick={() => void refreshHistory()}>Refresh</button></header>{historyItems.length ? <div className="inline-history-list">{historyItems.map((item) => <button type="button" key={`${item.kind}:${item.runId}`} className={item.runId === selectedHistoryRunId ? "active" : ""} onClick={() => handleSelectHistory(item)}><span className={`history-kind ${item.kind}`}>{item.kind === "finrisk" ? "Risk" : item.kind === "agent-runs" ? "Agent" : "Supply"}</span><strong>{item.title}</strong><small>{item.status}</small>{item.detail ? <em>{item.detail}</em> : null}</button>)}</div> : <p className="quiet-empty">No runs yet. Start research to create an auditable trail.</p>}</section>
              <LLMAgentRunPanel selectedRunId={selectedAgentRunId} staticMode={STATIC_DEMO_MODE} onProgress={(timeline) => { if (timeline) { setSelectedHistoryRunId(timeline.run_id); setHistoryItems((current) => [{ kind: "agent-runs", runId: timeline.run_id, status: timeline.status, title: "Supply-chain evidence review", detail: `${timeline.human_review_items.filter((item) => item.status === "pending").length} item(s) need analyst judgment` }, ...current.filter((item) => item.runId !== timeline.run_id)]); } setViewMonitor("agent-runs", agentRunSnapshot(timeline)); }} />
            </div>
          </main>
        ) : null}

        {route.page === "journal" ? (
          <main className="journal-page product-page" id="main-content" tabIndex={-1}>
            <header className="page-heading"><div><span className="page-eyebrow">Long-term research memory</span><h1>Journal</h1><p>Keep the thesis, disconfirming evidence, checkpoints and decisions in one traceable record.</p></div></header>
            <ResearchJournalPanel staticMode={STATIC_DEMO_MODE} />
          </main>
        ) : null}
        </Suspense>
      </div>

      {runPanelOpen ? (
        <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setRunPanelOpen(false); }}>
          <aside className="research-drawer" role="dialog" aria-modal="true" aria-labelledby="research-drawer-title">
            <header><div><span className="page-eyebrow">New company update</span><h2 id="research-drawer-title">Start research</h2><p>Define the question first. Runtime controls remain optional.</p></div><button type="button" autoFocus onClick={() => setRunPanelOpen(false)} aria-label="Close research panel"><X size={18} /></button></header>
            <WorkflowLauncher onStarted={handleStarted} busy={polling} staticMode={STATIC_DEMO_MODE} onLoadStaticDemo={() => { loadStaticDemo(); setRunPanelOpen(false); navigate({ page: "companies", section: "overview" }); }} />
          </aside>
        </div>
      ) : null}

      {activityOpen ? (
        <aside className="activity-drawer" role="dialog" aria-modal="false" aria-labelledby="activity-title">
          <header><div><span className="page-eyebrow">Current execution</span><h2 id="activity-title">Activity</h2></div><button type="button" autoFocus onClick={() => setActivityOpen(false)} aria-label="Close activity"><X size={18} /></button></header>
          <div className="activity-health"><ShieldCheck size={18} /><div><strong>{healthLabel}</strong><span>{serviceHealth === "partial" ? "The API did not answer the latest health check." : serviceHealth === "fixture" ? "This view uses offline fixture evidence." : "Latest health check completed."}</span></div></div>
          <section><span className="page-eyebrow">{activeMonitor.status ?? "idle"}</span><h3>{activeMonitor.title}</h3><ol className="activity-steps">{activeMonitor.nodes.map((node) => <li key={node.id} className={node.status}><span /><div><strong>{node.label}</strong><small>{node.log}</small></div></li>)}</ol></section>
          {summary ? <button className="product-secondary" type="button" onClick={() => { setActivityOpen(false); navigate({ page: "companies", section: "overview" }); }}>Open latest company brief</button> : null}
        </aside>
      ) : null}
    </div>
  );
}

export default App;
