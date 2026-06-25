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
  report_v16: RiskReportV16Wire | null;
  markdown: string | null;
  evaluation: WorkflowEvaluation | null;
}

export interface RiskReportV16Wire {
  title: string;
  executive_summary: string;
  top_risks: Array<{
    risk_id: string;
    title: string;
    risk_type: string;
    severity: number;
    final_score: number;
    summary: string;
    supporting_claim_ids: string[];
    supporting_evidence_ids: string[];
    related_graph_insight_ids: string[];
  }>;
  recent_changes: Array<{
    change_id: string;
    text: string;
    supporting_evidence_ids: string[];
    confidence: number;
  }>;
  evidence_table: Array<{
    evidence_id: string;
    source_name: string;
    source_url: string | null;
    quote_or_summary: string;
    source_quality_score: number;
  }>;
  second_order_effects: GraphInsightV16[];
  evidence_vs_inference: Array<{
    claim_id: string;
    text: string;
    claim_type: "evidence" | "inference" | "hypothesis";
    supporting_evidence_ids: string[];
    confidence: number;
  }>;
  limitations: string[];
  recommended_next_questions: string[];
  disclaimer: string;
  markdown: string | null;
}

// ---------------------------------------------------------------------------
// v16 types
// ---------------------------------------------------------------------------

export type GuardrailSeverityV16 = "info" | "warning" | "error" | "blocker";
export type GuardrailStatusV16 = "pass" | "warning" | "fail" | "needs_review";

export interface GuardrailFindingV16 {
  finding_id?: string;
  step_name: string;
  check_name: string;
  status: GuardrailStatusV16;
  severity: GuardrailSeverityV16;
  message: string;
  affected_object_type: string;
  affected_object_id?: string | null;
  recommendation?: string | null;
}

export interface FallbackEventV16 {
  event_id?: string;
  step_name: string;
  from_mode: string;
  to_mode: string;
  reason: string;
  occurred_at: string;
}

export interface StepEvaluationV16 {
  step_name: string;
  status: GuardrailStatusV16;
  findings: GuardrailFindingV16[];
  metrics?: Record<string, number>;
  latency_ms?: number | null;
  fallback_used?: string | null;
}

export interface WorkflowEvaluationV16 {
  run_id: string;
  final_status: GuardrailStatusV16;
  step_evaluations: StepEvaluationV16[];
  overall_metrics: Record<string, number>;
  blocker_count: number;
  warning_count: number;
  unsupported_claims: string[];
  human_review_required: boolean;
}

export interface GraphNodeV16 {
  node_id: string;
  node_type: string;
  label: string;
  properties?: Record<string, unknown>;
}

export interface GraphEdgeV16 {
  edge_id?: string;
  source_node_id: string;
  target_node_id: string;
  edge_type: string;
  metadata: {
    source?: string;
    evidence_ids?: string[];
    confidence?: number;
    extraction_method?: string;
  };
}

export interface GraphPathV16 {
  path_id: string;
  nodes: GraphNodeV16[];
  edges: GraphEdgeV16[];
  path_text: string;
  evidence_ids: string[];
  hop_count: number;
  path_score: number | null;
  score_breakdown?: Record<string, number>;
}

export interface GraphInsightV16 {
  insight_id?: string;
  source_company: string;
  insight_type: string;
  risk_path_ids: string[];
  affected_entities: string[];
  explanation: string;
  evidence_ids: string[];
  confidence: number;
  uncertainty?: string;
  recommended_next_questions?: string[];
  research_theme?: string | null;
}

export interface WorkflowTraceResponse {
  run_id: string;
  trace: WorkflowTraceEvent[];
  fallback_events: FallbackEventV16[];
}

export interface WorkflowGraphResponse {
  nodes: GraphNodeV16[];
  edges: GraphEdgeV16[];
  paths: GraphPathV16[];
  insights: GraphInsightV16[];
  guardrail_findings: GuardrailFindingV16[];
}

export interface WorkflowEvaluationResponse extends WorkflowEvaluationV16 {}

export interface WorkflowArtifactsResponse {
  run_id: string;
  artifacts: Record<string, string>;
}
