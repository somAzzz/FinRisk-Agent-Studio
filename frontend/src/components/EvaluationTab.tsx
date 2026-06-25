import { useState } from "react";
import { CheckCircle2, AlertTriangle, XCircle, Info } from "lucide-react";
import type {
  GuardrailFindingV16,
  StepEvaluationV16,
  WorkflowEvaluationV16,
} from "../types";

interface Props {
  evaluation: WorkflowEvaluationV16 | null;
}

const STATUS_LABELS: Record<WorkflowEvaluationV16["final_status"], string> = {
  pass: "Pass",
  warning: "Warning",
  fail: "Fail",
  needs_review: "Needs review",
};

function statusIcon(status: string) {
  if (status === "pass") return <CheckCircle2 size={14} color="#065f46" />;
  if (status === "needs_review" || status === "warning")
    return <AlertTriangle size={14} color="#92400e" />;
  if (status === "fail") return <XCircle size={14} color="#991b1b" />;
  return <Info size={14} color="#0f172a" />;
}

function severityClass(severity: string): string {
  if (severity === "blocker") return "evaluation-severity blocker";
  if (severity === "error") return "evaluation-severity error";
  if (severity === "warning") return "evaluation-severity warning";
  return "evaluation-severity info";
}

function FindingRow({ finding }: { finding: GuardrailFindingV16 }) {
  return (
    <details className="finding-row" data-testid={`finding-${finding.check_name}`}>
      <summary>
        <span className={severityClass(finding.severity)}>
          {finding.severity}
        </span>{" "}
        <strong>{finding.check_name}</strong>{" "}
        <span className="muted" style={{ fontSize: 11 }}>
          · {finding.step_name} · {finding.affected_object_type}
          {finding.affected_object_id ? `: ${finding.affected_object_id}` : ""}
        </span>
      </summary>
      <div className="finding-body">
        <p style={{ margin: "4px 0 6px 0" }}>{finding.message}</p>
        {finding.recommendation ? (
          <p className="muted" style={{ margin: 0, fontSize: 12 }}>
            Recommendation: {finding.recommendation}
          </p>
        ) : null}
      </div>
    </details>
  );
}

function StepRow({ step }: { step: StepEvaluationV16 }) {
  return (
    <li
      className="step-eval-row"
      data-testid={`step-eval-${step.step_name}`}
      data-step-status={step.status}
    >
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        {statusIcon(step.status)}
        <strong>{step.step_name}</strong>
      </span>
      <span className="muted" style={{ fontSize: 11 }}>
        {step.findings.length} finding{step.findings.length === 1 ? "" : "s"} ·
        latency {step.latency_ms ?? 0}ms
        {step.fallback_used ? ` · fallback=${step.fallback_used}` : ""}
      </span>
    </li>
  );
}

export function EvaluationTab({ evaluation }: Props) {
  const [drawerOpen, setDrawerOpen] = useState(true);
  if (!evaluation) {
    return (
      <div className="section empty-state" data-testid="evaluation-tab-empty">
        Evaluation will appear here once the workflow produces a v16
        evaluation.
      </div>
    );
  }
  const blockerFindings = evaluation.step_evaluations.flatMap((s) =>
    s.findings.filter((f) => f.severity === "blocker"),
  );
  const warningFindings = evaluation.step_evaluations.flatMap((s) =>
    s.findings.filter((f) => f.severity === "warning"),
  );
  return (
    <div className="section" data-testid="evaluation-tab">
      <h2>Evaluation</h2>
      <div
        className={`evaluation-banner ${evaluation.final_status === "needs_review" ? "needs_review" : evaluation.final_status}`}
        data-testid="evaluation-tab-status"
        data-final-status={evaluation.final_status}
      >
        <strong>{STATUS_LABELS[evaluation.final_status]}</strong>
        <span className="mono" style={{ fontSize: 12 }}>
          {evaluation.final_status}
        </span>
      </div>
      <div className="evaluation-metrics">
        <div>
          <div className="muted">Blockers</div>
          <div data-testid="metric-blockers">{evaluation.blocker_count}</div>
        </div>
        <div>
          <div className="muted">Warnings</div>
          <div data-testid="metric-warnings">{evaluation.warning_count}</div>
        </div>
        <div>
          <div className="muted">Human review</div>
          <div>
            {evaluation.human_review_required ? "required" : "not required"}
          </div>
        </div>
        <div>
          <div className="muted">Source diversity</div>
          <div>
            {(
              (evaluation.overall_metrics?.source_diversity as number) ?? 0
            ).toFixed(2)}
          </div>
        </div>
        <div>
          <div className="muted">Hallucination risk</div>
          <div>
            {(
              (evaluation.overall_metrics?.hallucination_risk as number) ?? 0
            ).toFixed(2)}
          </div>
        </div>
        <div>
          <div className="muted">Unsupported claims</div>
          <div>{evaluation.unsupported_claims.length}</div>
        </div>
      </div>

      <h3 style={{ marginTop: 16 }}>Step Quality Timeline</h3>
      <ul className="step-eval-list" data-testid="step-eval-list">
        {evaluation.step_evaluations.map((step) => (
          <StepRow key={step.step_name} step={step} />
        ))}
      </ul>

      <h3 style={{ marginTop: 16 }}>Guardrail Findings Drawer</h3>
      <button
        type="button"
        className="ghost"
        onClick={() => setDrawerOpen((o) => !o)}
        style={{ marginBottom: 8 }}
      >
        {drawerOpen ? "Hide" : "Show"} findings
      </button>
      {drawerOpen ? (
        <div data-testid="findings-drawer">
          {blockerFindings.length === 0 && warningFindings.length === 0 ? (
            <div className="muted">No blockers or warnings.</div>
          ) : (
            <>
              {blockerFindings.map((f, i) => (
                <FindingRow key={`b-${i}`} finding={f} />
              ))}
              {warningFindings.map((f, i) => (
                <FindingRow key={`w-${i}`} finding={f} />
              ))}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
