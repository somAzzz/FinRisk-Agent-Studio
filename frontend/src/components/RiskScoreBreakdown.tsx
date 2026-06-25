import type { RiskScore } from "../types";

interface Props {
  scores: RiskScore[];
}

const COMPONENT_KEYS: Array<{ key: keyof RiskScore; label: string }> = [
  { key: "base_severity", label: "base severity" },
  { key: "recent_signal_strength", label: "recent signal" },
  { key: "evidence_quality", label: "evidence quality" },
  { key: "source_diversity", label: "source diversity" },
  { key: "novelty_score", label: "novelty" },
  { key: "graph_centrality", label: "graph centrality" },
];

export function RiskScoreBreakdown({ scores }: Props) {
  if (!scores.length) {
    return (
      <div className="section empty-state" data-testid="risk-score-empty">
        No risk scores yet.
      </div>
    );
  }
  return (
    <div className="section" data-testid="risk-score-breakdown">
      <h2>Risk Score Breakdown</h2>
      <table
        style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}
      >
        <thead>
          <tr>
            <th style={th}>Risk</th>
            {COMPONENT_KEYS.map((c) => (
              <th key={String(c.key)} style={th}>
                {c.label}
              </th>
            ))}
            <th style={th}>Final (0-100)</th>
          </tr>
        </thead>
        <tbody>
          {scores.map((score) => (
            <tr key={score.risk_id} data-testid={`row-${score.risk_id}`}>
              <td style={td} className="mono">
                {score.risk_id}
              </td>
              {COMPONENT_KEYS.map((c) => (
                <td key={String(c.key)} style={td}>
                  {score[c.key] as number}
                </td>
              ))}
              <td style={td} data-testid={`final-${score.risk_id}`}>
                <strong>{score.final_score.toFixed(2)}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const th: React.CSSProperties = {
  border: "1px solid #e2e8f0",
  padding: "6px 8px",
  textAlign: "left",
  background: "#f8fafc",
};

const td: React.CSSProperties = {
  border: "1px solid #e2e8f0",
  padding: "6px 8px",
  verticalAlign: "top",
};
