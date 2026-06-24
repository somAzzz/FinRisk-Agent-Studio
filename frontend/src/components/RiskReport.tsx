import type {
  RiskReport as RiskReportType,
  RiskReportV16Wire,
} from "../types";

interface Props {
  report: RiskReportType | null;
  reportV16?: RiskReportV16Wire | null;
}

function severityClass(severity: number): string {
  return `severity-pill severity-${Math.max(1, Math.min(5, severity))}`;
}

function scoreForRisk(
  report: RiskReportType,
  riskId: string,
): number | undefined {
  return report.risk_scores.find((s) => s.risk_id === riskId)?.final_score;
}

export function RiskReport({ report, reportV16 }: Props) {
  if (reportV16) {
    return (
      <div className="section" data-testid="risk-report">
        <h2>Risk Report (v16)</h2>
        <h1 style={{ fontSize: 18, margin: "0 0 8px 0" }}>
          {reportV16.title}
        </h1>
        <p style={{ margin: "0 0 12px 0" }}>{reportV16.executive_summary}</p>
        <h3>Top Risks</h3>
        {reportV16.top_risks.map((item) => (
          <div
            className="risk-card"
            key={item.risk_id}
            data-testid={`risk-${item.risk_id}`}
          >
            <header>
              <div>
                <strong>{item.risk_type}</strong>{" "}
                <span className="risk-id mono">{item.risk_id}</span>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span
                  className="severity-pill"
                  data-testid={`score-${item.risk_id}`}
                >
                  score {item.final_score.toFixed(2)}
                </span>
                <span className={severityClass(item.severity)}>
                  severity {item.severity}/5
                </span>
              </div>
            </header>
            <div style={{ marginBottom: 8 }}>{item.summary}</div>
            {item.supporting_evidence_ids.length > 0 ? (
              <div className="muted" style={{ fontSize: 12 }}>
                Evidence: {item.supporting_evidence_ids.join(", ")}
              </div>
            ) : null}
          </div>
        ))}
        <h3>Disclaimer</h3>
        <p>{reportV16.disclaimer}</p>
      </div>
    );
  }
  if (!report) {
    return (
      <div className="section empty-state" data-testid="risk-report-empty">
        Report will appear here once the workflow finishes.
      </div>
    );
  }

  return (
    <div className="section" data-testid="risk-report">
      <h2>Risk Report</h2>
      <h1 style={{ fontSize: 18, margin: "0 0 8px 0" }}>{report.title}</h1>
      <p style={{ margin: "0 0 12px 0" }}>{report.executive_summary}</p>

      <h3>Top Risks</h3>
      {report.top_risks.map((risk) => {
        const score = scoreForRisk(report, risk.risk_id);
        return (
          <div className="risk-card" key={risk.risk_id} data-testid={`risk-${risk.risk_id}`}>
            <header>
              <div>
                <strong>{risk.risk_type}</strong>{" "}
                <span className="risk-id mono">{risk.risk_id}</span>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {score !== undefined ? (
                  <span className="severity-pill" data-testid={`score-${risk.risk_id}`}>
                    score {score.toFixed(2)}
                  </span>
                ) : null}
                <span className={severityClass(risk.severity)}>
                  severity {risk.severity}/5
                </span>
              </div>
            </header>
            <div style={{ marginBottom: 8 }}>{risk.risk_factor}</div>
            <blockquote
              style={{
                margin: 0,
                padding: "6px 12px",
                background: "#f1f5f9",
                borderLeft: "3px solid #10b981",
                fontSize: 13,
                color: "#334155",
              }}
            >
              “{risk.evidence_quote}” — {risk.source}
            </blockquote>
          </div>
        );
      })}

      <h3>Evidence Table</h3>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 12,
        }}
        data-testid="evidence-table"
      >
        <thead>
          <tr>
            <th style={th}>ID</th>
            <th style={th}>Source</th>
            <th style={th}>Type</th>
            <th style={th}>Summary</th>
          </tr>
        </thead>
        <tbody>
          {report.evidence_table.map((ev) => (
            <tr key={ev.evidence_id}>
              <td style={td} className="mono">{ev.evidence_id}</td>
              <td style={td}>
                {ev.source_url ? (
                  <a href={ev.source_url} target="_blank" rel="noreferrer">
                    {ev.source_name}
                  </a>
                ) : (
                  ev.source_name
                )}
              </td>
              <td style={td}>{ev.source_type}</td>
              <td style={td}>{ev.summary}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Second-Order Effects</h3>
      {report.graph_insights.length === 0 ? (
        <div className="muted">No second-order graph insights identified.</div>
      ) : (
        <ul className="evidence-list" data-testid="graph-insights">
          {report.graph_insights.map((ins) => (
            <li key={ins.insight_id}>
              <strong>{ins.source_company}</strong> → {ins.affected_entity}:{" "}
              {ins.risk_path.join(" → ")} (confidence {ins.confidence.toFixed(2)})
            </li>
          ))}
        </ul>
      )}

      <h3>Evidence vs Inference</h3>
      <div
        className="report-markdown"
        data-testid="evidence-vs-inference"
        style={{ whiteSpace: "pre-wrap" }}
      >
        {report.evidence_vs_inference}
      </div>

      <h3>Confidence & Limitations</h3>
      <div
        className="report-markdown"
        data-testid="limitations"
        style={{ whiteSpace: "pre-wrap" }}
      >
        {report.limitations}
      </div>

      <h3>Recommended Next Research Questions</h3>
      <ul className="evidence-list" data-testid="recommendations">
        {report.recommended_next_questions.map((q, i) => (
          <li key={i}>{q}</li>
        ))}
      </ul>
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
