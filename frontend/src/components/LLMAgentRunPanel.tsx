import { Check, Download, PlayCircle, RotateCw, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type {
  AgentEvidenceCandidateWire,
  AgentHumanReviewItemWire,
  AgentRunRequest,
  AgentRunSummary,
  AgentRunTimelineResponse,
  AgentRunTraceResponse,
  ToolExecutionEventWire,
} from "../types";

const DEFAULT_REQUEST: AgentRunRequest = {
  goal: "Find evidence about Apple's supply chain risk and cite sources.",
  workflow_kind: "finrisk",
  provider: "deepseek",
  tool_loop_mode: "auto",
  tool_scope: "finrisk_market",
  max_tool_rounds: 4,
  demo_mode: false,
  cached_mode: false,
  subject: { ticker: "AAPL", company_name: "Apple Inc." },
};

const TERMINAL_STATUSES = new Set(["completed", "failed", "needs_review"]);

type ParsedToolSummary = {
  data?: Record<string, unknown>;
  raw: string;
};

interface ToolDisplaySummary {
  action: string;
  outcome: string;
  detail: string;
  sources: Array<{ title: string; url?: string | null }>;
}

interface Props {
  onProgress?: (timeline: AgentRunTimelineResponse | null) => void;
  selectedRunId?: string | null;
}

function tryParseJson(value: string): unknown {
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return null;
  }
}

function parseToolSummary(summary: string): ParsedToolSummary {
  if (!summary.trim()) return { raw: "" };
  const parsed = tryParseJson(summary);
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    const data = parsed as Record<string, unknown>;
    const truncatedText = data.truncated_text;
    if (typeof truncatedText === "string") {
      const nested = tryParseJson(truncatedText);
      if (nested && typeof nested === "object" && !Array.isArray(nested)) {
        return {
          data: nested as Record<string, unknown>,
          raw: summary,
        };
      }
    }
    return {
      data,
      raw: summary,
    };
  }
  return { raw: summary };
}

function nestedValue(value: unknown, path: string[]): unknown {
  let current = value;
  for (const segment of path) {
    if (!current || typeof current !== "object" || Array.isArray(current)) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
}

function toolBadges(event: ToolExecutionEventWire): string[] {
  const parsed = parseToolSummary(event.result_summary);
  const data = parsed.data;
  const payload = data?.data;
  const badges: string[] = [];

  const graphSource = nestedValue(data, ["data", "graph_source"]);
  if (typeof graphSource === "string") badges.push(`graph: ${graphSource}`);

  const timedOut = nestedValue(data, ["data", "timed_out"]);
  if (timedOut === true) badges.push("browser timed out");

  const browserBackend = nestedValue(data, ["data", "browser_backend"]);
  if (typeof browserBackend === "string") badges.push(`browser: ${browserBackend}`);

  const resultCount = Array.isArray(nestedValue(data, ["data", "results"]))
    ? (nestedValue(data, ["data", "results"]) as unknown[]).length
    : undefined;
  if (typeof resultCount === "number") badges.push(`${resultCount} results`);

  const resultRows = Array.isArray(nestedValue(data, ["data", "results"]))
    ? (nestedValue(data, ["data", "results"]) as unknown[])
    : payload && typeof payload === "object" && !Array.isArray(payload)
      ? Object.values(payload as Record<string, unknown>)
      : [];
  if (resultRows.length) {
    const quality = resultRows
      .flatMap((row) => {
        if (!row || typeof row !== "object" || Array.isArray(row)) return [];
        const metadata = (row as Record<string, unknown>).metadata;
        if (!metadata || typeof metadata !== "object") return [];
        const score = (metadata as Record<string, unknown>).source_quality_score;
        return typeof score === "number" ? [score] : [];
      })[0];
    if (typeof quality === "number") {
      badges.push(`quality ${quality.toFixed(2)}`);
    }
  }

  if (event.truncated) badges.push("truncated");
  if (event.status === "failed") badges.push("failed");
  return badges;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function toolDisplaySummary(event: ToolExecutionEventWire): ToolDisplaySummary {
  const parsed = parseToolSummary(event.result_summary);
  const data = parsed.data ?? {};
  const payload = nestedValue(data, ["data"]) ?? data;
  const payloadObj =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? (payload as Record<string, unknown>)
      : {};
  const results = arrayValue(payloadObj.results);
  const paths = arrayValue(payloadObj.paths);
  const url = stringValue(payloadObj.url) ?? stringValue(event.arguments.url);
  const title =
    stringValue(payloadObj.title) ??
    stringValue(payloadObj.source_title) ??
    stringValue(event.arguments.query) ??
    event.tool_name;
  const error =
    event.error ??
    stringValue(payloadObj.error) ??
    stringValue((data as Record<string, unknown>).error);

  const sources = results.slice(0, 3).flatMap((row) => {
    if (!row || typeof row !== "object" || Array.isArray(row)) return [];
    const item = row as Record<string, unknown>;
    const sourceTitle = stringValue(item.title) ?? stringValue(item.url);
    if (!sourceTitle) return [];
    return [{ title: sourceTitle, url: stringValue(item.url) }];
  });
  if (!sources.length && url) {
    sources.push({ title, url });
  }

  if (event.status === "failed") {
    return {
      action: humanToolAction(event),
      outcome: "Tool did not run to completion.",
      detail: error ?? "No error detail was returned.",
      sources,
    };
  }
  if (results.length) {
    return {
      action: humanToolAction(event),
      outcome: `Found ${results.length} search result${results.length === 1 ? "" : "s"}.`,
      detail:
        sources[0]?.title ??
        stringValue(event.arguments.query) ??
        "Search completed with source-backed results.",
      sources,
    };
  }
  if (paths.length || event.tool_name.includes("graph")) {
    return {
      action: humanToolAction(event),
      outcome: paths.length
        ? `Found ${paths.length} graph path${paths.length === 1 ? "" : "s"}.`
        : "Graph checked; no paths returned.",
      detail: error ?? stringValue(payloadObj.graph_source) ?? "Graph query completed.",
      sources,
    };
  }
  if (url) {
    return {
      action: humanToolAction(event),
      outcome: "Fetched source content.",
      detail: title,
      sources,
    };
  }
  const compactRaw = shortText(
    parsed.raw.replace(/[{}"\\[\\]]/g, " ").replace(/\s+/g, " ").trim(),
    180,
  );
  return {
    action: humanToolAction(event),
    outcome: event.truncated ? "Result was truncated for budget control." : "Tool completed.",
    detail: error ?? (compactRaw || "No displayable result detail."),
    sources,
  };
}

function humanToolAction(event: ToolExecutionEventWire): string {
  const query = stringValue(event.arguments.query);
  const url = stringValue(event.arguments.url);
  if (event.tool_name.includes("search") && query) return `Searched: ${query}`;
  if (event.tool_name.includes("fetch") && url) return `Fetched: ${url}`;
  if (event.tool_name.includes("graph")) {
    const entity =
      stringValue(event.arguments.entity) ??
      stringValue(event.arguments.source_entity) ??
      "target entity";
    return `Queried graph around ${entity}`;
  }
  return event.tool_name.split("_").join(" ");
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function shortText(value: string, max = 260): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max)}...`;
}

function evidenceId(candidate: AgentEvidenceCandidateWire): string {
  return candidate.evidence_id ?? candidate.candidate_id ?? "candidate";
}

function hostFromUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export function LLMAgentRunPanel({ onProgress, selectedRunId }: Props = {}) {
  const [request, setRequest] = useState<AgentRunRequest>(DEFAULT_REQUEST);
  const [summary, setSummary] = useState<AgentRunSummary | null>(null);
  const [timeline, setTimeline] = useState<AgentRunTimelineResponse | null>(null);
  const [trace, setTrace] = useState<AgentRunTraceResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const budgetUsage = trace?.tool_traces?.find((item) => item.budget_usage)
    ?.budget_usage;
  const acceptedCount = trace?.accepted_evidence_ids?.length ?? 0;
  const failedToolCount = timeline?.tool_events.filter((e) => e.status === "failed")
    .length ?? 0;
  const reviewCount = timeline?.human_review_items.filter(
    (item) => item.status === "pending",
  ).length ?? 0;

  const traceHref = useMemo(() => {
    if (!summary) return null;
    return summary.trace_url;
  }, [summary]);

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => {
    return () => stopPolling();
  }, []);

  const refresh = async (
    runId = summary?.run_id,
  ): Promise<AgentRunTimelineResponse | null> => {
    if (!runId) return null;
    const [nextTimeline, nextTrace] = await Promise.all([
      api.getAgentRunTimeline(runId),
      api.getAgentRunTrace(runId),
    ]);
    setTimeline(nextTimeline);
    setTrace(nextTrace);
    onProgress?.(nextTimeline);
    if (TERMINAL_STATUSES.has(nextTimeline.status)) {
      stopPolling();
      setBusy(false);
    }
    return nextTimeline;
  };

  const startPolling = (runId: string) => {
    stopPolling();
    void refresh(runId).catch((err) => {
      setError((err as Error).message);
      setBusy(false);
      stopPolling();
    });
    pollRef.current = window.setInterval(() => {
      void refresh(runId).catch((err) => {
        setError((err as Error).message);
        setBusy(false);
        stopPolling();
      });
    }, 1500);
  };

  useEffect(() => {
    if (!selectedRunId || selectedRunId === summary?.run_id) return;
    stopPolling();
    setBusy(true);
    setError(null);
    setSummary({
      run_id: selectedRunId,
      status: "running",
      timeline_url: `/agent-runs/${selectedRunId}/timeline`,
      trace_url: `/agent-runs/${selectedRunId}/trace.json`,
    });
    void refresh(selectedRunId)
      .catch((err) => setError((err as Error).message))
      .finally(() => setBusy(false));
  }, [selectedRunId]);

  const run = async () => {
    setBusy(true);
    setError(null);
    setTimeline(null);
    setTrace(null);
    onProgress?.(null);
    try {
      const nextSummary = await api.startAgentRun(request);
      setSummary(nextSummary);
      startPolling(nextSummary.run_id);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  const review = async (
    item: AgentHumanReviewItemWire,
    action: "approve" | "reject",
  ) => {
    if (!summary) return;
    setBusy(true);
    setError(null);
    try {
      await api.reviewAgentRunItem(summary.run_id, item.item_id, { action });
      await refresh(summary.run_id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const reviewCandidate = async (
    candidate: AgentEvidenceCandidateWire,
    action: "approve" | "reject",
  ) => {
    if (!summary) return;
    setBusy(true);
    setError(null);
    try {
      await api.reviewAgentRunCandidate(summary.run_id, evidenceId(candidate), {
        action,
      });
      await refresh(summary.run_id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="agent-run-view" data-testid="llm-agent-run-panel">
      <aside className="agent-run-controls">
        <form
          className="section"
          onSubmit={(event) => {
            event.preventDefault();
            void run();
          }}
        >
          <h2>LLM Agent Run</h2>
          <div className="row stacked">
            <label htmlFor="agent-goal">Goal</label>
            <textarea
              id="agent-goal"
              data-testid="agent-goal-input"
              value={request.goal}
              onChange={(event) =>
                setRequest((current) => ({
                  ...current,
                  goal: event.target.value,
                }))
              }
            />
          </div>
          <div className="row">
            <label htmlFor="agent-workflow">Workflow</label>
            <select
              id="agent-workflow"
              value={request.workflow_kind}
              onChange={(event) =>
                setRequest((current) => ({
                  ...current,
                  workflow_kind: event.target.value as AgentRunRequest["workflow_kind"],
                }))
              }
            >
              <option value="finrisk">FinRisk</option>
              <option value="supply_chain">Supply Chain</option>
              <option value="company_research">Company Research</option>
              <option value="generic_research">Generic Research</option>
            </select>
          </div>
          <div className="row">
            <label htmlFor="agent-provider">Provider</label>
            <select
              id="agent-provider"
              data-testid="agent-provider-select"
              value={request.provider}
              onChange={(event) =>
                setRequest((current) => ({
                  ...current,
                  provider: event.target.value as AgentRunRequest["provider"],
                }))
              }
            >
              <option value="deepseek">DeepSeek</option>
              <option value="vllm">vLLM</option>
              <option value="sglang">SGLang</option>
            </select>
          </div>
          <div className="row">
            <label htmlFor="agent-tool-scope">Tools</label>
            <select
              id="agent-tool-scope"
              value={request.tool_scope ?? "finrisk_market"}
              onChange={(event) =>
                setRequest((current) => ({
                  ...current,
                  tool_scope: event.target.value as AgentRunRequest["tool_scope"],
                }))
              }
            >
              <option value="finrisk_market">FinRisk market</option>
              <option value="supply_chain">Supply chain</option>
              <option value="company_research">Company research</option>
            </select>
          </div>
          <div className="row">
            <label htmlFor="agent-tool-mode">Tool loop</label>
            <select
              id="agent-tool-mode"
              value={request.tool_loop_mode ?? "auto"}
              onChange={(event) =>
                setRequest((current) => ({
                  ...current,
                  tool_loop_mode: event.target.value as AgentRunRequest["tool_loop_mode"],
                }))
              }
            >
              <option value="auto">Auto</option>
              <option value="native">Native</option>
              <option value="json_fallback">JSON fallback</option>
            </select>
          </div>
          <div className="row">
            <label htmlFor="agent-rounds">Max rounds</label>
            <input
              id="agent-rounds"
              type="number"
              min={0}
              max={10}
              value={request.max_tool_rounds ?? 4}
              onChange={(event) =>
                setRequest((current) => ({
                  ...current,
                  max_tool_rounds: Number(event.target.value) || 0,
                }))
              }
            />
          </div>
          <button
            type="submit"
            className="primary icon-button"
            disabled={busy || !request.goal.trim()}
            data-testid="agent-run-button"
          >
            <PlayCircle size={15} />
            {busy ? "Running..." : "Run Agent"}
          </button>
          {summary ? (
            <button
              type="button"
              className="ghost icon-button full-width"
              disabled={busy}
              onClick={() => void refresh()}
              data-testid="agent-refresh-button"
            >
              <RotateCw size={14} />
              Refresh timeline
            </button>
          ) : null}
          {error ? (
            <div className="error-banner" data-testid="agent-error">
              {error}
            </div>
          ) : null}
        </form>
      </aside>

      <main className="agent-run-main">
        <section className="section agent-run-summary">
          <h2>Run State</h2>
          {summary ? (
            <>
              <div className="agent-run-kpis">
                <div>
                  <span className="kpi-label">Status</span>
                  <strong data-testid="agent-status">{timeline?.status ?? summary.status}</strong>
                </div>
                <div>
                  <span className="kpi-label">Tools</span>
                  <strong>{timeline?.tool_events.length ?? 0}</strong>
                </div>
                <div>
                  <span className="kpi-label">Accepted evidence</span>
                  <strong>{acceptedCount}</strong>
                </div>
                <div>
                  <span className="kpi-label">Review</span>
                  <strong>{reviewCount}</strong>
                </div>
              </div>
              <div className="agent-run-links">
                <span className="mono">{summary.run_id}</span>
                {traceHref ? (
                  <a href={traceHref} target="_blank" rel="noreferrer">
                    <Download size={14} />
                    trace.json
                  </a>
                ) : null}
              </div>
              {budgetUsage ? (
                <div className="budget-strip" data-testid="agent-budget">
                  <span>
                    tool result budget{" "}
                    <strong>
                      {budgetUsage.used_tool_result_chars}/
                      {budgetUsage.max_total_tool_result_chars}
                    </strong>
                  </span>
                  <span>{budgetUsage.truncated_events} truncated</span>
                  <span>{failedToolCount} failed</span>
                </div>
              ) : null}
              {trace?.fallback_events?.length ? (
                <ul className="agent-fallbacks">
                  {trace.fallback_events.map((event) => (
                    <li key={event}>{event}</li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <div className="empty-state">
              Run a local agent loop to inspect planner decisions, tool calls,
              evidence candidates, and review items.
            </div>
          )}
        </section>

        {timeline ? (
          <>
            <section className="section">
              <h2>Subgoals</h2>
              <div className="agent-subgoal-list">
                {timeline.subgoals.map((subgoal) => (
                  <article
                    className="agent-subgoal"
                    key={subgoal.subgoal_id}
                    data-testid={`agent-subgoal-${subgoal.subgoal_id}`}
                  >
                    <header>
                      <strong>{subgoal.objective}</strong>
                      <span className={`status-pill ${subgoal.status}`}>
                        {subgoal.status}
                      </span>
                    </header>
                    <div className="muted">
                      scope <span className="mono">{subgoal.tool_scope}</span> ·
                      attempts {subgoal.attempt_count}
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="section">
              <h2>Tool Trace</h2>
              <div className="tool-event-list">
                {timeline.tool_events.map((event) => (
                  <ToolEventCard event={event} key={event.event_id} />
                ))}
              </div>
            </section>

            <AgentEvidenceGraph timeline={timeline} />

            <section className="section">
              <h2>Evidence Candidates</h2>
              <div className="candidate-grid">
                {timeline.evidence_candidates.length ? (
                  timeline.evidence_candidates.map((candidate) => (
                    <EvidenceCandidateCard
                      candidate={candidate}
                      key={evidenceId(candidate)}
                      busy={busy}
                      onReview={reviewCandidate}
                    />
                  ))
                ) : (
                  <div className="empty-state">No evidence candidates yet.</div>
                )}
              </div>
            </section>

            <section className="section">
              <h2>Human Review</h2>
              {timeline.human_review_items.length ? (
                <div className="review-list">
                  {timeline.human_review_items.map((item) => (
                    <article className="review-item" key={item.item_id}>
                      <header>
                        <strong>{item.object_type}</strong>
                        <span className={`status-pill ${item.status}`}>
                          {item.status}
                        </span>
                      </header>
                      <p>{item.reason}</p>
                      <div className="review-actions">
                        <button
                          type="button"
                          className="ghost icon-button"
                          disabled={busy || item.status !== "pending"}
                          onClick={() => void review(item, "approve")}
                        >
                          <Check size={14} />
                          Approve
                        </button>
                        <button
                          type="button"
                          className="ghost icon-button"
                          disabled={busy || item.status !== "pending"}
                          onClick={() => void review(item, "reject")}
                        >
                          <X size={14} />
                          Reject
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state">No pending review items.</div>
              )}
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}

function ToolEventCard({ event }: { event: ToolExecutionEventWire }) {
  const badges = toolBadges(event);
  const summary = toolDisplaySummary(event);
  return (
    <article
      className={`tool-event ${event.status}`}
      data-testid={`tool-event-${event.tool_name}`}
    >
      <header>
        <div>
          <strong>{event.tool_name}</strong>
          <span className="mono"> {event.round_id}</span>
        </div>
        <span className={`status-pill ${event.status}`}>{event.status}</span>
      </header>
      <div className="tool-meta">
        <span>{formatMs(event.latency_ms)}</span>
        <span>{event.result_chars} chars</span>
        <span>{event.round_id}</span>
        {event.error ? <span>{event.error}</span> : null}
      </div>
      {badges.length ? (
        <div className="tool-badges">
          {badges.map((badge) => (
            <span key={badge}>{badge}</span>
          ))}
        </div>
      ) : null}
      <div className="tool-readable">
        <strong>{summary.action}</strong>
        <span>{summary.outcome}</span>
        <p>{summary.detail}</p>
        {summary.sources.length ? (
          <ul>
            {summary.sources.map((source) => (
              <li key={`${source.title}:${source.url ?? ""}`}>
                {source.url ? (
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.title}
                  </a>
                ) : (
                  source.title
                )}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </article>
  );
}

function EvidenceCandidateCard({
  candidate,
  busy,
  onReview,
}: {
  candidate: AgentEvidenceCandidateWire;
  busy: boolean;
  onReview: (
    candidate: AgentEvidenceCandidateWire,
    action: "approve" | "reject",
  ) => void;
}) {
  const needsReview = candidate.status === "needs_review";
  const sourceName =
    candidate.source_name ??
    candidate.source_title ??
    hostFromUrl(candidate.source_url);
  return (
    <article className="candidate-card" data-testid="agent-evidence-candidate">
      <header>
        <strong>{evidenceId(candidate)}</strong>
        <span className={`status-pill ${candidate.status ?? "unknown"}`}>
          {candidate.status ?? "unknown"}
        </span>
      </header>
      <p>{candidate.summary ?? candidate.quote ?? "No summary"}</p>
      {candidate.rejection_reason ? (
        <div className="candidate-reason">
          {candidate.status === "rejected" ? "Rejected" : "Review reason"}:{" "}
          {candidate.rejection_reason}
        </div>
      ) : null}
      <div className="candidate-meta">
        {candidate.kind ? <span>{candidate.kind}</span> : null}
        {typeof candidate.source_quality_score === "number" ? (
          <span>quality {candidate.source_quality_score.toFixed(2)}</span>
        ) : null}
        {typeof candidate.grounding_score === "number" ? (
          <span>grounding {candidate.grounding_score.toFixed(2)}</span>
        ) : null}
      </div>
      {candidate.source_url ? (
        <a href={candidate.source_url} target="_blank" rel="noreferrer">
          {sourceName ?? candidate.source_url}
        </a>
      ) : null}
      {needsReview ? (
        <div className="review-actions candidate-actions">
          <button
            type="button"
            className="ghost icon-button"
            disabled={busy}
            onClick={() => onReview(candidate, "approve")}
          >
            <Check size={14} />
            Approve
          </button>
          <button
            type="button"
            className="ghost icon-button"
            disabled={busy}
            onClick={() => onReview(candidate, "reject")}
          >
            <X size={14} />
            Reject
          </button>
        </div>
      ) : null}
    </article>
  );
}

function AgentEvidenceGraph({
  timeline,
}: {
  timeline: AgentRunTimelineResponse;
}) {
  const eventById = new Map(
    timeline.tool_events.map((event) => [event.event_id, event]),
  );
  const visibleCandidates = timeline.evidence_candidates.slice(0, 8);
  if (!timeline.subgoals.length && !timeline.tool_events.length && !visibleCandidates.length) {
    return null;
  }
  return (
    <section className="section agent-evidence-graph" data-testid="agent-evidence-graph">
      <h2>Evidence Graph</h2>
      <div className="agent-graph-columns">
        <div>
          <span className="agent-graph-label">Subgoals</span>
          {timeline.subgoals.map((subgoal) => (
            <div className={`agent-graph-node ${subgoal.status}`} key={subgoal.subgoal_id}>
              <strong>{subgoal.objective}</strong>
              <span>{subgoal.tool_scope}</span>
            </div>
          ))}
        </div>
        <div>
          <span className="agent-graph-label">Tools</span>
          {timeline.tool_events.slice(0, 10).map((event) => (
            <div className={`agent-graph-node ${event.status}`} key={event.event_id}>
              <strong>{event.tool_name}</strong>
              <span>{humanToolAction(event)}</span>
            </div>
          ))}
        </div>
        <div>
          <span className="agent-graph-label">Evidence</span>
          {visibleCandidates.map((candidate) => {
            const event = candidate.source_event_id
              ? eventById.get(candidate.source_event_id)
              : null;
            return (
              <div
                className={`agent-graph-node ${candidate.status ?? "unknown"}`}
                key={evidenceId(candidate)}
              >
                <strong>{candidate.source_title ?? evidenceId(candidate)}</strong>
                <span>
                  {candidate.kind ?? "evidence"}
                  {event ? ` via ${event.tool_name}` : ""}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
