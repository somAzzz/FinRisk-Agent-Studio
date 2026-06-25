// LifecycleBadge — small reusable pill that renders the lifecycle
// classification (current / emerging / receding / unknown) for one
// extracted risk. Surfaced on every top-risk card in RiskReport.tsx
// and used by StepOutputInspector to mark each row in the lifecycle
// list.

import type { RiskLifecycle } from "../types";

interface Props {
  lifecycle: RiskLifecycle | undefined;
  confidence?: number;
  reasoning?: string;
}

const LABEL: Record<RiskLifecycle, string> = {
  current: "Current",
  emerging: "Emerging",
  receding: "Receding",
  unknown: "Unknown",
};

const COLOR: Record<RiskLifecycle, { dot: string; bg: string; fg: string }> = {
  current: { dot: "#10b981", bg: "rgba(16,185,129,0.12)", fg: "#047857" },
  emerging: { dot: "#f59e0b", bg: "rgba(245,158,11,0.14)", fg: "#b45309" },
  receding: { dot: "#9ca3af", bg: "rgba(156,163,175,0.16)", fg: "#4b5563" },
  unknown: { dot: "#cbd5e1", bg: "rgba(203,213,225,0.18)", fg: "#475569" },
};

export function LifecycleBadge({ lifecycle, confidence, reasoning }: Props) {
  const lc: RiskLifecycle = lifecycle ?? "unknown";
  const c = COLOR[lc];
  const tooltip = reasoning
    ? `${LABEL[lc]} (conf ${(confidence ?? 0).toFixed(2)}): ${reasoning}`
    : `${LABEL[lc]}${confidence !== undefined ? ` (conf ${confidence.toFixed(2)})` : ""}`;
  return (
    <span
      className="lifecycle-badge"
      title={tooltip}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "2px 8px",
        borderRadius: 999,
        background: c.bg,
        color: c.fg,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: 1.4,
      }}
      data-testid={`lifecycle-badge-${lc}`}
    >
      <span
        aria-hidden
        style={{
          width: 7,
          height: 7,
          borderRadius: 999,
          background: c.dot,
          display: "inline-block",
        }}
      />
      {LABEL[lc]}
      {confidence !== undefined && (
        <span style={{ opacity: 0.7, fontWeight: 400 }}>
          {Math.round(confidence * 100)}%
        </span>
      )}
    </span>
  );
}
