import { CheckCircle2, Loader2, XCircle, MinusCircle } from "lucide-react";
import type { WorkflowStatusResponse, WorkflowTraceEvent } from "../types";

interface Props {
  status: WorkflowStatusResponse | null;
}

const STATUS_ORDER: string[] = [
  "company_resolver",
  "filing_risk_extractor",
  "market_explorer",
  "evidence_normalizer",
  "risk_scorer",
  "graph_reasoner",
  "report_generator",
  "evaluator",
];

function statusIconClass(status: WorkflowTraceEvent["status"]): string {
  return `icon ${status}`;
}

function StatusIcon({ status }: { status: WorkflowTraceEvent["status"] }) {
  if (status === "completed") return <CheckCircle2 size={14} />;
  if (status === "running") return <Loader2 size={14} className="spin" />;
  if (status === "failed") return <XCircle size={14} />;
  return <MinusCircle size={14} />;
}

function formatDuration(
  startedAt: string,
  completedAt: string | null | undefined,
): string {
  if (!completedAt) return "...";
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

export function AgentTimeline({ status }: Props) {
  const events = status?.trace ?? [];
  const eventByName = new Map(events.map((e) => [e.step_name, e]));

  return (
    <div className="section" data-testid="agent-timeline">
      <h2>Agent Timeline</h2>
      <ul className="timeline">
        {STATUS_ORDER.map((name) => {
          const event = eventByName.get(name);
          const traceStatus: WorkflowTraceEvent["status"] = event?.status ?? "skipped";
          return (
            <li
              key={name}
              className="timeline-item"
              data-testid={`step-${name}`}
              data-step-status={traceStatus}
            >
              <span className={statusIconClass(traceStatus)}>
                <StatusIcon status={traceStatus} />
              </span>
              <div className="body">
                <div className="name">{name}</div>
                <div className="meta">
                  started {event ? formatTime(event.started_at) : "—"}
                  {event?.error ? ` · error: ${event.error}` : ""}
                </div>
              </div>
              <div className="duration">
                {event
                  ? formatDuration(event.started_at, event.completed_at)
                  : "—"}
              </div>
            </li>
          );
        })}
      </ul>
      {status ? (
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          Workflow status: <span className="mono">{status.status}</span>
        </div>
      ) : null}
    </div>
  );
}
