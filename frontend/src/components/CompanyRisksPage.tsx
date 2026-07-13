import { useMemo, useState } from "react";
import { ArrowRight, FileText, ShieldAlert } from "lucide-react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RiskReport as RiskReportType, RiskReportV16Wire } from "../types";
import type { OverviewRiskRow } from "./ResearchDecisionBrief";
import { RiskReport } from "./RiskReport";

interface Props {
  report: RiskReportV16Wire | null;
  legacyReport: RiskReportType | null;
  risks: OverviewRiskRow[];
  onReviewEvidence: () => void;
}

export function CompanyRisksPage({ report, legacyReport, risks, onReviewEvidence }: Props) {
  const [selectedId, setSelectedId] = useState(risks[0]?.id ?? "");
  const selectedIndex = Math.max(0, risks.findIndex((risk) => risk.id === selectedId));
  const selected = risks[selectedIndex] ?? risks[0];
  const reportRisk = report?.top_risks[selectedIndex] ?? report?.top_risks[0] ?? null;
  const evidenceIds = reportRisk?.supporting_evidence_ids ?? [];
  const evidence = useMemo(
    () => report?.evidence_table.filter((item) => evidenceIds.includes(item.evidence_id)) ?? [],
    [evidenceIds, report],
  );
  const trendData = selected?.trend.map((value, index) => ({ day: `D${index + 1}`, value })) ?? [];

  if (!selected) {
    return <div className="directed-empty"><ShieldAlert size={24} /><div><strong>No ranked risks yet.</strong><p>Run a company update to create an evidence-linked risk baseline.</p></div></div>;
  }

  return (
    <div className="risk-workspace">
      <section className="risk-ledger-panel">
        <header className="section-heading-row">
          <div><span className="page-eyebrow">{risks.length} monitored</span><h2>Risk ledger</h2></div>
          <span className="count-chip">Priority</span>
        </header>
        <div className="risk-ledger-head" aria-hidden="true"><span>Risk</span><span>Score</span><span>7D</span></div>
        <div className="risk-ledger-list">
          {risks.map((risk, index) => (
            <button type="button" key={risk.id} className={risk.id === selected.id ? "active" : ""} aria-pressed={risk.id === selected.id} onClick={() => setSelectedId(risk.id)}>
              <span className={`rank-number rank-${Math.min(index + 1, 4)}`}>{index + 1}</span>
              <span><strong>{risk.title}</strong><small>{risk.summary}</small></span>
              <b>{risk.score.toFixed(1)}</b>
              <em className={risk.change >= 0 ? "up" : "down"}>{risk.change >= 0 ? "+" : ""}{risk.change.toFixed(1)}</em>
            </button>
          ))}
        </div>
      </section>

      <section className="risk-detail-panel">
        <header>
          <div><span className="page-eyebrow">Selected risk</span><h2>{selected.title}</h2><p>{selected.summary}</p></div>
          <div className="risk-detail-score"><strong>{selected.score.toFixed(1)}</strong><span>/100</span><small>{selected.confidence} confidence</small></div>
        </header>

        <div className="risk-detail-grid">
          <div className="risk-trend-card">
            <span>Research priority · 7 days</span>
            <div className="risk-trend-chart" role="img" aria-label={`${selected.title} seven-day research priority trend`}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData} margin={{ top: 10, right: 8, bottom: 0, left: -24 }}>
                  <XAxis dataKey="day" tick={{ fontSize: 9, fill: "#687b8d" }} axisLine={false} tickLine={false} />
                  <YAxis domain={["dataMin - 4", "dataMax + 4"]} tick={{ fontSize: 9, fill: "#687b8d" }} axisLine={false} tickLine={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" stroke={selected.change >= 0 ? "#c2413d" : "#1f7a7a"} strokeWidth={2.2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <dl className="risk-facts">
            <div><dt>7D change</dt><dd className={selected.change >= 0 ? "up" : "down"}>{selected.change >= 0 ? "+" : ""}{selected.change.toFixed(1)}</dd></div>
            <div><dt>Lifecycle</dt><dd>{reportRisk?.lifecycle ?? "current"}</dd></div>
            <div><dt>Severity</dt><dd>{reportRisk?.severity ?? "—"} / 5</dd></div>
            <div><dt>Evidence</dt><dd>{evidenceIds.length}</dd></div>
          </dl>
        </div>

        <div className="risk-analysis-columns">
          <section>
            <h3>Why this matters</h3>
            <p>{reportRisk?.summary ?? selected.summary}</p>
            <h3>Financial transmission</h3>
            <p>{report?.financial_impacts?.[selectedIndex]?.drivers.join(" → ") || "volume → cost → working capital"}</p>
            <small>Affected metrics: {report?.financial_impacts?.[selectedIndex]?.affected_metrics.join(", ") || "revenue, gross margin, free cash flow"}</small>
          </section>
          <section>
            <h3>Supporting evidence</h3>
            {evidence.length ? evidence.map((item) => (
              <article className="risk-evidence-row" key={item.evidence_id}>
                <FileText size={15} aria-hidden="true" />
                <div><strong>{item.source_name}</strong><p>{item.quote_or_summary}</p><small>{item.evidence_id} · {Math.round(item.source_quality_score * 100)}% quality</small></div>
              </article>
            )) : <p className="quiet-empty">The compact fixture links evidence through the Evidence workspace.</p>}
            <button className="product-secondary" type="button" onClick={onReviewEvidence}>Review all evidence <ArrowRight size={14} /></button>
          </section>
        </div>

        <section className="next-diligence-strip">
          <div><span className="page-eyebrow">Next diligence</span><strong>{report?.recommended_next_questions[0] ?? "Review the newest primary evidence."}</strong></div>
          <button className="text-action" type="button" onClick={onReviewEvidence}>Open evidence</button>
        </section>
      </section>

      <details className="full-risk-report">
        <summary>Open full generated report</summary>
        <RiskReport report={report ? null : legacyReport} reportV16={report} />
      </details>
    </div>
  );
}
