import type { WorkflowEvaluation } from "../types";

interface Props {
  evaluation: WorkflowEvaluation | null;
}

const LABELS: Record<WorkflowEvaluation["final_status"], string> = {
  pass: "Pass",
  needs_review: "Needs review",
  fail: "Fail",
};

export function EvaluationPanel({ evaluation }: Props) {
  if (!evaluation) {
    return (
      <div className="section empty-state" data-testid="evaluation-empty">
        Evaluation will appear here once the workflow finishes.
      </div>
    );
  }

  const cls = evaluation.final_status;
  return (
    <div className="section" data-testid="evaluation-panel">
      <h2>Evaluation</h2>
      <div
        className={`evaluation-banner ${cls}`}
        data-testid="evaluation-status"
        data-final-status={cls}
      >
        <strong>{LABELS[evaluation.final_status]}</strong>
        <span className="mono" style={{ fontSize: 12 }}>
          {evaluation.final_status}
        </span>
      </div>
      <div className="evaluation-metrics">
        <div>
          <div className="muted">Schema valid</div>
          <div data-testid="metric-schema">
            {evaluation.schema_valid ? "yes" : "no"}
          </div>
        </div>
        <div>
          <div className="muted">Evidence per risk</div>
          <div data-testid="metric-evidence">
            {evaluation.has_evidence_for_each_risk ? "yes" : "no"}
          </div>
        </div>
        <div>
          <div className="muted">Advice risk</div>
          <div data-testid="metric-advice">
            {evaluation.financial_advice_risk ? "yes" : "no"}
          </div>
        </div>
        <div>
          <div className="muted">Source diversity</div>
          <div data-testid="metric-diversity">
            {evaluation.source_diversity_score.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="muted">Hallucination risk</div>
          <div data-testid="metric-hallucination">
            {evaluation.hallucination_risk_score.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="muted">Unsupported claims</div>
          <div data-testid="metric-unsupported">
            {evaluation.unsupported_claims.length}
          </div>
        </div>
      </div>
      {evaluation.unsupported_claims.length > 0 ? (
        <ul className="evidence-list" style={{ marginTop: 10 }}>
          {evaluation.unsupported_claims.map((c, i) => (
            <li key={i} className="mono" style={{ fontSize: 12 }}>
              {c}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
