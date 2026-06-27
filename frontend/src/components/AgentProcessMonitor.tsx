import { useState } from "react";
import {
  Activity,
  CheckCircle2,
  Clock3,
  MinusCircle,
  PanelLeftOpen,
  PanelRightClose,
  XCircle,
} from "lucide-react";

export type ProcessNodeStatus =
  | "queued"
  | "running"
  | "completed"
  | "needs_review"
  | "failed"
  | "skipped";

export interface ProcessNode {
  id: string;
  label: string;
  status: ProcessNodeStatus;
  log: string;
  meta?: string;
}

export interface ProcessMonitorSnapshot {
  title: string;
  runId?: string | null;
  status?: string | null;
  nodes: ProcessNode[];
}

interface Props {
  snapshot: ProcessMonitorSnapshot;
}

function statusIcon(status: ProcessNodeStatus) {
  if (status === "completed") return <CheckCircle2 size={13} />;
  if (status === "running") return <Activity size={13} />;
  if (status === "failed") return <XCircle size={13} />;
  if (status === "needs_review") return <Clock3 size={13} />;
  return <MinusCircle size={13} />;
}

export function AgentProcessMonitor({ snapshot }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const activeIndex = snapshot.nodes.findIndex((node) => node.status === "running");
  const fallbackIndex = snapshot.nodes.findIndex((node) =>
    ["needs_review", "failed"].includes(node.status),
  );
  const lastCompletedIndex = snapshot.nodes.reduce(
    (last, node, index) => (node.status === "completed" ? index : last),
    -1,
  );
  const currentIndex =
    activeIndex >= 0
      ? activeIndex
      : fallbackIndex >= 0
        ? fallbackIndex
        : Math.max(0, lastCompletedIndex);
  const currentNode = snapshot.nodes[currentIndex];

  return (
    <aside
      className={`process-monitor dock-panel ${collapsed ? "collapsed" : ""}`}
      aria-label="Agent process monitor"
      data-collapsed={collapsed ? "true" : "false"}
    >
      <button
        type="button"
        className="dock-toggle right-dock"
        onClick={() => setCollapsed((current) => !current)}
        aria-label={collapsed ? "Show agent process monitor" : "Hide agent process monitor"}
        aria-expanded={!collapsed}
      >
        {collapsed ? <PanelLeftOpen size={15} /> : <PanelRightClose size={15} />}
      </button>
      <header>
        <div>
          <span className="monitor-kicker">Current agent</span>
          <strong>{snapshot.title}</strong>
        </div>
        <span className={`monitor-status ${snapshot.status ?? "queued"}`}>
          {snapshot.status ?? "idle"}
        </span>
      </header>
      <div className="monitor-current">
        <span>Now</span>
        <strong>{currentNode?.label ?? "Waiting for run"}</strong>
      </div>
      <ol className="monitor-nodes">
        {snapshot.nodes.map((node, index) => (
          <li
            key={node.id}
            className={`monitor-node ${node.status}`}
            data-current={index === currentIndex ? "true" : "false"}
            tabIndex={0}
          >
            <span className="monitor-node-icon">{statusIcon(node.status)}</span>
            <span className="monitor-node-label">{node.label}</span>
            <span className="monitor-node-log" role="tooltip">
              <strong>{node.label}</strong>
              <span>{node.log}</span>
              {node.meta ? <em>{node.meta}</em> : null}
            </span>
          </li>
        ))}
      </ol>
      {snapshot.runId ? (
        <footer className="monitor-run-id">{snapshot.runId}</footer>
      ) : null}
    </aside>
  );
}
