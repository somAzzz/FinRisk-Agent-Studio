import { AlertTriangle, CheckCircle2, FileText, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import type { WorkflowEvaluation, WorkflowEvaluationResponse } from "../types";
import type { ClaimRow } from "./ClaimEvidenceMatrix";

interface Props {
  evaluation: WorkflowEvaluation | WorkflowEvaluationResponse | null;
  claims: ClaimRow[];
  graphContent?: ReactNode;
  staticMode?: boolean;
}

const demoClaims: ClaimRow[] = [
  { claim_id: "claim-1", claim_type: "evidence", text: "Manufacturing remains concentrated among a limited number of partners and regions.", supporting_evidence_ids: ["10-K-2025", "sc-ev-5"], grounding: "grounded", status: "pass", recommendation: null },
  { claim_id: "claim-2", claim_type: "inference", text: "India expansion reduces single-region exposure, but transition execution creates near-term operational risk.", supporting_evidence_ids: ["sc-ev-1", "ev-mgmt-1"], grounding: "grounded", status: "pass", recommendation: null },
  { claim_id: "claim-3", claim_type: "hypothesis", text: "Export controls could constrain access to leading-edge semiconductor capacity.", supporting_evidence_ids: ["sc-ev-2"], grounding: "needs_review", status: "needs_review", recommendation: "Confirm against the latest export-control notices." },
];

const demoSources = [
  { type: "SEC filing", title: "Apple Inc. 2025 Form 10-K", date: "2025-10-31", quality: "High", claims: 4 },
  { type: "Company filing", title: "TSMC 2025 Annual Report", date: "2026-03-10", quality: "High", claims: 2 },
  { type: "Transcript", title: "Apple FY2026 Q3 earnings call", date: "2026-07-08", quality: "High", claims: 3 },
  { type: "Supplier disclosure", title: "OLED capacity and customer mix", date: "2026-06-22", quality: "Medium", claims: 1 },
];

export function CompanyEvidencePage({ evaluation, claims, graphContent, staticMode = false }: Props) {
  const visibleClaims = claims.length ? claims : staticMode ? demoClaims : [];
  const grounded = visibleClaims.filter((claim) => claim.grounding === "grounded").length;
  const legacyEvaluation = evaluation && "hallucination_risk_score" in evaluation ? evaluation : null;
  const modernEvaluation = evaluation && "overall_metrics" in evaluation ? evaluation : null;
  const qualityScore = legacyEvaluation ? Math.round((1 - legacyEvaluation.hallucination_risk_score) * 100) : modernEvaluation ? Math.round((modernEvaluation.overall_metrics.source_quality ?? .9) * 100) : staticMode ? 90 : 0;
  const sourceDiversity = legacyEvaluation ? Math.round(legacyEvaluation.source_diversity_score * 100) : modernEvaluation ? Math.round((modernEvaluation.overall_metrics.evidence_coverage ?? .86) * 100) : staticMode ? 86 : 0;
  const unsupported = evaluation?.unsupported_claims.length ?? visibleClaims.filter((claim) => claim.grounding === "unsupported").length;

  return (
    <div className="evidence-workspace">
      <section className="evidence-health-panel">
        <header><div><span className="page-eyebrow">Release gate</span><h2>Evidence quality</h2></div><span className={`evidence-gate ${evaluation?.final_status ?? "needs_review"}`}><ShieldCheck size={14} />{evaluation?.final_status === "pass" ? "Ready" : "Analyst review"}</span></header>
        <div className="evidence-kpis">
          <article><span>Confidence score</span><strong>{qualityScore}<small>/100</small></strong><p>Adjusted for unsupported-claim risk</p></article>
          <article><span>Claims grounded</span><strong>{grounded}<small>/{visibleClaims.length || 0}</small></strong><p>Linked to retrievable evidence</p></article>
          <article><span>Source diversity</span><strong>{sourceDiversity}<small>%</small></strong><p>Primary and independent coverage</p></article>
          <article><span>Unsupported</span><strong>{unsupported}</strong><p>Requires evidence before reliance</p></article>
        </div>
      </section>

      <section className="claim-coverage-panel">
        <header className="section-heading-row"><div><span className="page-eyebrow">Decision traceability</span><h2>Claim coverage</h2></div><span className="count-chip">{visibleClaims.length} claims</span></header>
        {visibleClaims.length ? <div className="claim-coverage-list">{visibleClaims.map((claim) => (
          <article key={claim.claim_id}>
            <span className={`claim-state ${claim.grounding}`}>{claim.grounding === "grounded" ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}{claim.grounding.replace("_", " ")}</span>
            <div><strong>{claim.text}</strong><small>{claim.claim_type} · {claim.claim_id}</small></div>
            <div className="claim-evidence-links">{claim.supporting_evidence_ids.map((id) => <span key={id}>{id}</span>)}</div>
            <p>{claim.recommendation ?? "Evidence linkage meets the current review threshold."}</p>
          </article>
        ))}</div> : <p className="quiet-empty">No surfaced claims yet. Complete a company update to build the evidence matrix.</p>}
      </section>

      <section className="source-inventory-panel">
        <header className="section-heading-row"><div><span className="page-eyebrow">Retrievable records</span><h2>Source inventory</h2></div><span className="count-chip">{staticMode ? 147 : "Live"} items</span></header>
        <div className="source-inventory-list">{(staticMode ? demoSources : demoSources.slice(0, 0)).map((source) => (
          <article key={source.title}><FileText size={17} /><div><strong>{source.title}</strong><small>{source.type} · Published {source.date}</small></div><span className={`source-quality ${source.quality.toLowerCase()}`}>{source.quality}</span><b>{source.claims} claims</b></article>
        ))}</div>
        {!staticMode ? <p className="quiet-empty">Source inventory is populated from the selected live run.</p> : null}
      </section>

      {graphContent ? <details className="evidence-technical"><summary><span>Evidence graph and technical evaluation</span><small>Inspect paths, nodes and guardrail detail</small></summary><div>{graphContent}</div></details> : null}
    </div>
  );
}
