import type {
  RiskReport as RiskReportType,
  RiskReportV16Wire,
} from "../types";
import { LifecycleBadge } from "./LifecycleBadge";

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
        <h2>Risk Intelligence Report</h2>
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
                  priority {item.final_score.toFixed(2)}
                </span>
                <span className={severityClass(item.severity)}>
                  severity {item.severity}/5
                </span>
                <LifecycleBadge
                  lifecycle={item.lifecycle}
                  confidence={item.lifecycle_confidence}
                  reasoning={item.lifecycle_reasoning}
                />
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
        <h3>Recent Changes</h3>
        {reportV16.recent_changes.length ? (
          <ul className="evidence-list" data-testid="v16-recent-changes">
            {reportV16.recent_changes.map((change) => (
              <li key={change.change_id}>
                {change.text} <span className="muted">({Math.round(change.confidence * 100)}% confidence)</span>
              </li>
            ))}
          </ul>
        ) : <p className="muted">No recent change has been evidenced.</p>}

        <h3>Evidence Register</h3>
        <div className="table-scroll">
          <table className="research-table" data-testid="v16-evidence-table">
            <thead><tr><th>ID</th><th>Source</th><th>Evidence</th><th>Quality</th></tr></thead>
            <tbody>
              {reportV16.evidence_table.map((item) => (
                <tr key={item.evidence_id}>
                  <td className="mono">{item.evidence_id}</td>
                  <td>{item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer">{item.source_name}</a> : item.source_name}</td>
                  <td>{item.quote_or_summary}</td>
                  <td>{Math.round(item.source_quality_score * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3>Second-Order Effects</h3>
        {reportV16.second_order_effects.length ? (
          <div className="insight-grid" data-testid="v16-second-order-effects">
            {reportV16.second_order_effects.map((insight, index) => (
              <article className="insight-card" key={insight.insight_id ?? `${insight.source_company}-${index}`}>
                <div className="insight-card-meta">{insight.insight_type} · {Math.round(insight.confidence * 100)}%</div>
                <strong>{insight.affected_entities.join(" → ") || insight.source_company}</strong>
                <p>{insight.explanation}</p>
                {insight.uncertainty ? <small>Uncertainty: {insight.uncertainty}</small> : null}
              </article>
            ))}
          </div>
        ) : <p className="muted">No evidence-backed second-order effect identified.</p>}

        <h3>Evidence, Inference & Hypothesis</h3>
        <div className="claim-list" data-testid="v16-claims">
          {reportV16.evidence_vs_inference.map((claim) => (
            <article key={claim.claim_id} className={`claim-row ${claim.claim_type}`}>
              <span>{claim.claim_type}</span>
              <div><strong>{claim.text}</strong><small>{claim.supporting_evidence_ids.join(", ") || "No linked evidence"}</small></div>
              <b>{Math.round(claim.confidence * 100)}%</b>
            </article>
          ))}
        </div>

        <h3>Financial Impact Channels</h3>
        {(reportV16.financial_impacts ?? []).length ? (
          <div className="impact-grid" data-testid="v16-financial-impacts">
            {(reportV16.financial_impacts ?? []).map((impact) => (
              <article className="impact-card" key={impact.risk_id}>
                <header>
                  <strong>{impact.risk_id}</strong>
                  <span>{impact.quantification_status}</span>
                </header>
                <p>{impact.drivers.join(" → ") || "Impact channel unknown"}</p>
                <small>Affected: {impact.affected_metrics.join(", ") || "not mapped"}</small>
                <small>{impact.rationale}</small>
              </article>
            ))}
          </div>
        ) : <p className="muted">Financial impact has not been mapped yet.</p>}

        <h3>Limitations</h3>
        <ul className="evidence-list" data-testid="v16-limitations">
          {reportV16.limitations.map((item) => <li key={item}>{item}</li>)}
        </ul>

        <h3>Recommended Next Research Questions</h3>
        <ol className="evidence-list" data-testid="v16-recommendations">
          {reportV16.recommended_next_questions.map((item) => <li key={item}>{item}</li>)}
        </ol>
        <h3>Disclaimer</h3>
        <p className="report-disclaimer">{reportV16.disclaimer}</p>
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
