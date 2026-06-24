// Shared TypeScript types mirroring the FinRisk backend Pydantic models.
// The shapes stay in sync with src/schemas/finrisk.py and src/api/workflows.py.

export type WorkflowStatus =
  | "queued"
  | "running"
  | "completed"
  | "needs_review"
  | "failed"
  | "created";

export type StepStatus = "completed" | "running" | "failed" | "skipped";

export interface FinRiskRequest {
  ticker: string;
  company_name?: string | null;
  analysis_goal: string;
  time_horizon?: string;
  year?: number | null;
  sources?: Array<"filing" | "web" | "transcript" | "graph">;
  max_browser_steps?: number;
  demo_mode?: boolean;
  cached_mode?: boolean;
}

export interface WorkflowRunSummary {
  run_id: string;
  status: WorkflowStatus;
  current_step?: string | null;
  started_at: string;
  completed_at?: string | null;
  report_url?: string | null;
}

export interface WorkflowTraceEvent {
  step_name: string;
  status: StepStatus;
  started_at: string;
  completed_at?: string | null;
  error?: string | null;
}

export interface CompanyProfile {
  company_name: string;
  ticker: string;
  cik: string;
  filing_type: string;
  analysis_year: number;
  source: string;
  resolved_at: string;
}

export interface RiskScore {
  risk_id: string;
  base_severity: number;
  recent_signal_strength: number;
  evidence_quality: number;
  source_diversity: number;
  novelty_score: number;
  graph_centrality?: number | null;
  final_score: number;
  score_reasoning: string;
}

export interface ExtractedRisk {
  risk_id: string;
  risk_type: string;
  risk_factor: string;
  severity: number;
  evidence_quote: string;
  source: string;
  filing_section?: string | null;
  confidence: number;
}

export interface NormalizedEvidence {
  evidence_id: string;
  source_type: string;
  source_name: string;
  source_url?: string | null;
  quote?: string | null;
  summary: string;
  related_risk_ids?: string[];
  credibility_score?: number;
}

export interface GraphInsight {
  insight_id: string;
  source_company: string;
  affected_entity: string;
  risk_path: string[];
  investment_theme?: string | null;
  supporting_evidence_ids: string[];
  confidence: number;
}

export interface RiskReport {
  title: string;
  executive_summary: string;
  top_risks: ExtractedRisk[];
  risk_scores: RiskScore[];
  evidence_table: NormalizedEvidence[];
  graph_insights: GraphInsight[];
  evidence_vs_inference: string;
  limitations: string;
  recommended_next_questions: string[];
  markdown: string;
}

export interface WorkflowEvaluation {
  schema_valid: boolean;
  has_evidence_for_each_risk: boolean;
  unsupported_claims: string[];
  financial_advice_risk: boolean;
  source_diversity_score: number;
  hallucination_risk_score: number;
  final_status: "pass" | "needs_review" | "fail";
}

export interface WorkflowStatusResponse {
  run_id: string;
  status: WorkflowStatus;
  current_step?: string | null;
  trace: WorkflowTraceEvent[];
  company: CompanyProfile | null;
  risk_count: number;
  evidence_count: number;
  evaluation: WorkflowEvaluation | null;
  completed_at?: string | null;
}

export interface WorkflowReportResponse {
  run_id: string;
  status: WorkflowStatus;
  report: RiskReport | null;
  markdown: string | null;
  evaluation: WorkflowEvaluation | null;
}
