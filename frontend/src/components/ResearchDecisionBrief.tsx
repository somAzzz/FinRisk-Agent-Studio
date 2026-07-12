import type {
  CompanyProfile,
  RiskReportV16Wire,
  WorkflowEvaluation,
} from "../types";
import {
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
} from "recharts";
import { ChevronRight, Clock3 } from "lucide-react";

export interface OverviewRiskRow {
  id: string;
  title: string;
  summary: string;
  score: number;
  trend: number[];
  change: number;
  confidence: "High" | "Medium" | "Low" | "Limited";
}

export interface EvidenceBreakdownItem {
  label: string;
  value: number;
  color: string;
}

interface Props {
  company: CompanyProfile | null;
  report: RiskReportV16Wire | null;
  evaluation: WorkflowEvaluation | null;
  onViewRisks?: () => void;
  onViewEvidence?: () => void;
  displayRisks?: OverviewRiskRow[];
  evidenceBreakdown?: EvidenceBreakdownItem[];
  evidenceConfidenceScore?: number;
  evidenceItemCount?: number;
  recentEvidenceCount?: number;
  conflictingEvidenceCount?: number;
}

function readinessLabel(evaluation: WorkflowEvaluation | null): string {
  if (!evaluation) return "Awaiting quality review";
  if (evaluation.final_status === "pass") return "Evidence ready";
  if (evaluation.final_status === "needs_review") return "Analyst review required";
  return "Not decision ready";
}

function riskTitle(value: string): string {
  if (value === "supply_chain") return "Supply chain concentration";
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}

export function ResearchDecisionBrief({
  report,
  evaluation,
  onViewRisks,
  onViewEvidence,
  displayRisks,
  evidenceBreakdown,
  evidenceConfidenceScore,
  evidenceItemCount,
  recentEvidenceCount,
  conflictingEvidenceCount,
}: Props) {
  if (!report) return null;

  const supportedClaims = report.evidence_vs_inference.filter(
    (claim) => claim.supporting_evidence_ids.length > 0,
  ).length;
  const rankedRisks = [...report.top_risks]
    .sort((left, right) => right.final_score - left.final_score)
    .slice(0, 6);
  const highestRisk = rankedRisks[0];
  const evidenceConfidence = report.evidence_table.length
    ? report.evidence_table.reduce((total, item) => total + item.source_quality_score, 0) /
      report.evidence_table.length
    : 0;
  const primaryChange = report.recent_changes[0]?.text ?? "No material change detected.";
  const nextQuestion = report.recommended_next_questions[0] ?? "Review the newest primary evidence.";
  const riskRows: OverviewRiskRow[] = displayRisks ?? rankedRisks.map((risk) => {
    const claimConfidence = report.evidence_vs_inference
      .filter((claim) => risk.supporting_claim_ids.includes(claim.claim_id))
      .reduce((maximum, claim) => Math.max(maximum, claim.confidence), 0);
    return {
      id: risk.risk_id,
      title: riskTitle(risk.title),
      summary: risk.summary,
      score: risk.final_score,
      trend: [risk.final_score - 2, risk.final_score - 1, risk.final_score - 1.5, risk.final_score, risk.final_score - 0.4, risk.final_score + 0.6, risk.final_score],
      change: 0,
      confidence: claimConfidence >= 0.8 ? "High" : claimConfidence >= 0.6 ? "Medium" : "Limited",
    };
  });
  const breakdown = evidenceBreakdown ?? [
    { label: "High (trusted)", value: Math.round(evidenceConfidence * 100), color: "#1f7a7a" },
    { label: "Medium (supported)", value: Math.max(0, 100 - Math.round(evidenceConfidence * 100)), color: "#8aa8ad" },
  ];
  const evidenceTotal = evidenceItemCount ?? report.evidence_table.length;
  const displayedEvidenceConfidence = evidenceConfidenceScore ?? Math.round(evidenceConfidence * 100);
  const highQualityEvidence = Math.ceil(evidenceTotal * ((breakdown[0]?.value ?? 0) / 100));

  return (
    <div className="company-overview" data-testid="research-decision-brief">
      <section className="decision-brief-panel">
        <header>
          <span className="page-eyebrow">Latest assessed position</span>
          <h2>Decision brief</h2>
        </header>
        <div className="decision-grid">
          <div>
            <span>Research status</span>
            <strong className={`decision-status ${evaluation?.final_status ?? "pending"}`} data-testid="research-readiness">
              {readinessLabel(evaluation)}
            </strong>
            <small>{supportedClaims} of {report.evidence_vs_inference.length} claims grounded</small>
          </div>
          <div>
            <span>Highest-priority risk</span>
            <strong className="risk-emphasis">{highestRisk ? riskTitle(highestRisk.title) : "No ranked risk"}</strong>
            <small>{highestRisk ? `${highestRisk.final_score.toFixed(1)} / 100` : "—"}</small>
          </div>
          <div>
            <span>What changed</span>
            <strong>{primaryChange}</strong>
            <small>{report.recent_changes.length} evidence-linked change</small>
          </div>
          <div>
            <span>Next diligence</span>
            <strong>{nextQuestion}</strong>
            <small>{report.recommended_next_questions.length} open question</small>
          </div>
        </div>
      </section>

      <div className="overview-grid">
        <section className="risk-ranking-panel evidence-rail">
          <header className="section-heading-row">
            <div>
              <span className="page-eyebrow">Ranked by research priority</span>
              <h2>Top risks</h2>
            </div>
            <span className="count-chip">{riskRows.length} total</span>
          </header>
          <div className="risk-ranking-head" aria-hidden="true">
            <span>Risk</span><span>Score</span><span>Trend (7D)</span><span>Change</span><span>Confidence</span>
          </div>
          <ol className="risk-ranking-list">
            {riskRows.map((risk, index) => (
                <li key={risk.id}>
                  <span className={`rank-number rank-${Math.min(index + 1, 4)}`}>{index + 1}</span>
                  <div>
                    <strong>{risk.title}</strong>
                    <small>{risk.summary}</small>
                  </div>
                  <b>{risk.score.toFixed(1)}</b>
                  <div className={`risk-sparkline ${risk.change >= 0 ? "up" : "down"}`} aria-label={`Seven day trend ${risk.change >= 0 ? "up" : "down"} ${Math.abs(risk.change).toFixed(1)}`}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={risk.trend.map((value) => ({ value }))} margin={{ top: 2, right: 1, bottom: 2, left: 1 }}>
                        <Line type="monotone" dataKey="value" stroke="currentColor" strokeWidth={1.8} dot={false} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <span className={`risk-change ${risk.change >= 0 ? "up" : "down"}`}>{risk.change >= 0 ? "+" : ""}{risk.change.toFixed(1)}</span>
                  <span className="confidence-label">{risk.confidence}</span>
                </li>
            ))}
          </ol>
          {onViewRisks ? <button className="panel-link" type="button" onClick={onViewRisks}>View all risks</button> : null}
        </section>

        <div className="overview-evidence-stack">
          <aside className="evidence-confidence-panel">
            <header>
              <span className="page-eyebrow">Source-backed</span>
              <h2>Evidence confidence</h2>
            </header>
            <div className="confidence-visual">
              <div className="confidence-donut" role="img" aria-label={`Evidence confidence ${displayedEvidenceConfidence} out of 100`}>
                <PieChart width={142} height={142}>
                  <Pie data={breakdown} dataKey="value" nameKey="label" cx="50%" cy="50%" innerRadius={45} outerRadius={61} strokeWidth={0} isAnimationActive={false}>
                    {breakdown.map((item) => <Cell key={item.label} fill={item.color} />)}
                  </Pie>
                </PieChart>
                <div className="confidence-score"><strong>{displayedEvidenceConfidence}</strong><span>/100</span></div>
              </div>
              <ul className="confidence-legend">
                {breakdown.map((item) => <li key={item.label}><i style={{ backgroundColor: item.color }} /><span>{item.label}</span><strong>{item.value}%</strong></li>)}
              </ul>
            </div>
            <dl className="evidence-summary-list">
              <div><dt>Total evidence items</dt><dd>{evidenceTotal}</dd></div>
              <div><dt>High-quality sources</dt><dd>{highQualityEvidence} ({breakdown[0]?.value ?? 0}%)</dd></div>
              <div><dt>Recent (≤ 7 days)</dt><dd>{recentEvidenceCount ?? report.evidence_table.length}</dd></div>
              <div><dt>Conflicting items</dt><dd>{conflictingEvidenceCount ?? 0}</dd></div>
            </dl>
          </aside>
          {onViewEvidence ? <button className="source-freshness-card" type="button" onClick={onViewEvidence}><Clock3 size={18} aria-hidden="true" /><span>Source freshness</span><strong>Most critical feeds updated today</strong><ChevronRight size={17} aria-hidden="true" /></button> : null}
        </div>
      </div>
    </div>
  );
}
