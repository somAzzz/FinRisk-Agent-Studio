import type {
  CompanyProfile,
  RiskReportV16Wire,
  WorkflowEvaluation,
} from "../types";

interface Props {
  company: CompanyProfile | null;
  report: RiskReportV16Wire | null;
  evaluation: WorkflowEvaluation | null;
}

function readinessLabel(evaluation: WorkflowEvaluation | null): string {
  if (!evaluation) return "Awaiting quality review";
  if (evaluation.final_status === "pass") return "Evidence ready";
  if (evaluation.final_status === "needs_review") return "Analyst review required";
  return "Not decision ready";
}

export function ResearchDecisionBrief({ company, report, evaluation }: Props) {
  if (!report) return null;

  const supportedClaims = report.evidence_vs_inference.filter(
    (claim) => claim.supporting_evidence_ids.length > 0,
  ).length;
  const claimCoverage = report.evidence_vs_inference.length
    ? supportedClaims / report.evidence_vs_inference.length
    : 0;
  const sourceCount = new Set(report.evidence_table.map((item) => item.source_name)).size;
  const highestRisk = [...report.top_risks].sort(
    (left, right) => right.final_score - left.final_score,
  )[0];

  return (
    <section className="research-brief" data-testid="research-decision-brief">
      <div className="research-brief-heading">
        <div>
          <span className="research-eyebrow">Analyst decision ledger</span>
          <h2>
            {company?.company_name ?? report.title}
            {company?.ticker ? <span className="ticker-tag">{company.ticker}</span> : null}
          </h2>
          <p>{report.executive_summary}</p>
        </div>
        <div
          className={`readiness-stamp ${evaluation?.final_status ?? "pending"}`}
          data-testid="research-readiness"
        >
          <span>Research status</span>
          <strong>{readinessLabel(evaluation)}</strong>
        </div>
      </div>

      <div className="research-ledger-grid">
        <div>
          <span>Highest-priority risk</span>
          <strong>{highestRisk?.title ?? "No ranked risk"}</strong>
          <small>{highestRisk ? `${highestRisk.final_score.toFixed(1)} / 100` : "—"}</small>
        </div>
        <div>
          <span>Evidence sources</span>
          <strong>{sourceCount}</strong>
          <small>{report.evidence_table.length} evidence records</small>
        </div>
        <div>
          <span>Claim coverage</span>
          <strong>{Math.round(claimCoverage * 100)}%</strong>
          <small>{supportedClaims} claims linked to evidence</small>
        </div>
        <div>
          <span>Recent changes</span>
          <strong>{report.recent_changes.length}</strong>
          <small>{report.recommended_next_questions.length} open questions</small>
        </div>
      </div>

      <div className="research-brief-columns">
        <div>
          <h3>What changed</h3>
          {report.recent_changes.length ? (
            <ul>
              {report.recent_changes.slice(0, 3).map((change) => (
                <li key={change.change_id}>{change.text}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">No recent change has been evidenced yet.</p>
          )}
        </div>
        <div>
          <h3>Next diligence</h3>
          {report.recommended_next_questions.length ? (
            <ol>
              {report.recommended_next_questions.slice(0, 3).map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ol>
          ) : (
            <p className="muted">No follow-up question has been generated.</p>
          )}
        </div>
      </div>
    </section>
  );
}
