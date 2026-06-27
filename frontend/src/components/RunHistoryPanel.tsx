import { useState } from "react";
import { Clock3, PanelRightOpen, PanelLeftClose, RotateCw } from "lucide-react";
import type { RunHistoryKind } from "../types";

export interface RunHistoryItem {
  kind: RunHistoryKind;
  runId: string;
  status: string;
  title: string;
  detail?: string | null;
}

interface Props {
  items: RunHistoryItem[];
  selectedRunId?: string | null;
  onSelect: (item: RunHistoryItem) => void;
  onRefresh: () => void;
}

function kindLabel(kind: RunHistoryKind): string {
  if (kind === "finrisk") return "Risk";
  if (kind === "agent-runs") return "Agent";
  return "Supply";
}

export function RunHistoryPanel({
  items,
  selectedRunId,
  onSelect,
  onRefresh,
}: Props) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <section
      className={`run-history dock-panel ${collapsed ? "collapsed" : ""}`}
      aria-label="Run history"
      data-collapsed={collapsed ? "true" : "false"}
    >
      <button
        type="button"
        className="dock-toggle left-dock"
        onClick={() => setCollapsed((current) => !current)}
        aria-label={collapsed ? "Show run history" : "Hide run history"}
        aria-expanded={!collapsed}
      >
        {collapsed ? <PanelRightOpen size={15} /> : <PanelLeftClose size={15} />}
      </button>
      <header>
        <div>
          <span>History</span>
          <strong>Recent runs</strong>
        </div>
        <button
          type="button"
          className="ghost icon-button"
          onClick={onRefresh}
          aria-label="Refresh run history"
        >
          <RotateCw size={13} />
        </button>
      </header>
      {items.length ? (
        <div className="run-history-list">
          {items.map((item) => (
            <button
              type="button"
              key={`${item.kind}:${item.runId}`}
              className={item.runId === selectedRunId ? "active" : ""}
              onClick={() => onSelect(item)}
            >
              <span className="history-kind">{kindLabel(item.kind)}</span>
              <span className="history-main">
                <strong>{item.title}</strong>
                <em>{item.runId}</em>
              </span>
              <span className={`history-status ${item.status}`}>
                {item.status}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="run-history-empty">
          <Clock3 size={14} />
          No runs yet
        </div>
      )}
    </section>
  );
}
