import { Check, Download, PlayCircle, RotateCw, X } from "lucide-react";
import { useMemo, useState } from "react";
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

type ParsedToolSummary = {
  data?: Record<string, unknown>;
  raw: string;
};

function parseToolSummary(summary: string): ParsedToolSummary {
  if (!summary.trim()) return { raw: "" };
  try {
    const parsed = JSON.parse(summary) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return {
        data: parsed as Record<string, unknown>,
        raw: summary,
      };
    }
  } catch {
    // Keep the raw text below.
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

export function LLMAgentRunPanel() {
  const [request, setRequest] = useState<AgentRunRequest>(DEFAULT_REQUEST);
  const [summary, setSummary] = useState<AgentRunSummary | null>(null);
  const [timeline, setTimeline] = useState<AgentRunTimelineResponse | null>(null);
  const [trace, setTrace] = useState<AgentRunTraceResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const refresh = async (runId = summary?.run_id) => {
    if (!runId) return;
    const [nextTimeline, nextTrace] = await Promise.all([
      api.getAgentRunTimeline(runId),
      api.getAgentRunTrace(runId),
    ]);
    setTimeline(nextTimeline);
    setTrace(nextTrace);
  };

  const run = async () => {
    setBusy(true);
    setError(null);
    setTimeline(null);
    setTrace(null);
    try {
      const nextSummary = await api.startAgentRun(request);
      setSummary(nextSummary);
      await refresh(nextSummary.run_id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
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

            <section className="section">
              <h2>Evidence Candidates</h2>
              <div className="candidate-grid">
                {timeline.evidence_candidates.length ? (
                  timeline.evidence_candidates.map((candidate) => (
                    <EvidenceCandidateCard
                      candidate={candidate}
                      key={evidenceId(candidate)}
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
  const parsed = parseToolSummary(event.result_summary);
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
        {event.error ? <span>{event.error}</span> : null}
      </div>
      {badges.length ? (
        <div className="tool-badges">
          {badges.map((badge) => (
            <span key={badge}>{badge}</span>
          ))}
        </div>
      ) : null}
      <pre>{shortText(parsed.raw)}</pre>
    </article>
  );
}

function EvidenceCandidateCard({
  candidate,
}: {
  candidate: AgentEvidenceCandidateWire;
}) {
  return (
    <article className="candidate-card" data-testid="agent-evidence-candidate">
      <header>
        <strong>{evidenceId(candidate)}</strong>
        <span className={`status-pill ${candidate.status ?? "unknown"}`}>
          {candidate.status ?? "unknown"}
        </span>
      </header>
      <p>{candidate.summary ?? candidate.quote ?? "No summary"}</p>
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
          {candidate.source_name ?? candidate.source_url}
        </a>
      ) : null}
    </article>
  );
}
