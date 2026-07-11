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
  llm_config?: LLMRunConfig;
}

export type LLMProvider = "sglang" | "vllm" | "deepseek" | "openai";

export interface LLMRunConfig {
  provider: LLMProvider;
  base_url?: string | null;
  model?: string | null;
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
  novelty_available?: boolean;
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
  // Lifecycle classification (added 2026-06-25). Populated by
  // LifecycleClassifierStep; missing for risks extracted before
  // the step was added.
  lifecycle?: RiskLifecycle;
  lifecycle_confidence?: number;
  lifecycle_reasoning?: string;
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
    lifecycle?: RiskLifecycle;
    lifecycle_confidence?: number;
    lifecycle_reasoning?: string;
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
  financial_impacts?: Array<{
    risk_id: string;
    affected_segment?: string | null;
    drivers: string[];
    affected_metrics: string[];
    direction: "adverse" | "favorable" | "mixed" | "unknown";
    time_horizon: string;
    evidence_ids: string[];
    evidence_quote: string;
    confidence: number;
    quantification_status: "unquantified" | "quantified";
    probability?: number | null;
    estimated_impact?: number | null;
    assumptions: string[];
    rationale: string;
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
  // Per-step observability slices (added 2026-06-25).
  llm_log: LLMCall[];
  chunk_validations: ChunkValidation[];
  section_locations: SectionLocation[];
  risk_lifecycles: RiskLifecycleAnnotation[];
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

export type FinancialPeriodKind =
  | "quarter"
  | "year_to_date"
  | "annual"
  | "ttm"
  | "instant"
  | "unknown";

export interface FinancialMetricPoint {
  metric: string;
  value: number;
  unit: string;
  period_end: string;
  period_start?: string | null;
  period_kind: FinancialPeriodKind;
  fiscal_year?: number | null;
  fiscal_period?: string | null;
  form_type?: string | null;
  accession_number?: string | null;
  filed_at?: string | null;
  source_concept: string;
  status: "reported" | "derived";
  derivation?: string | null;
  source_accession_numbers: string[];
}

export interface FinancialChange {
  metric: string;
  change_type: "qoq" | "yoy" | "annual_yoy" | "ttm_yoy";
  current_period_end: string;
  comparison_period_end: string;
  current_value: number;
  comparison_value: number;
  absolute_change: number;
  percent_change?: number | null;
  unit: string;
  source_accession_numbers: string[];
}

export interface FinancialSnapshot {
  ticker: string;
  cik: string;
  company_name?: string | null;
  as_of: string;
  currency: string;
  metrics: FinancialMetricPoint[];
  changes: FinancialChange[];
  warnings: string[];
}

export interface Catalyst {
  catalyst_id: string;
  title: string;
  expected_date?: string | null;
  status: "upcoming" | "occurred" | "missed" | "cancelled";
  evidence_ids: string[];
}

export interface ThesisReview {
  review_id: string;
  reviewed_at: string;
  outcome: "supported" | "mixed" | "invalidated" | "unknown";
  notes: string;
  evidence_ids: string[];
}

export interface InvestmentThesis {
  thesis_id: string;
  ticker: string;
  statement: string;
  time_horizon: string;
  status: "draft" | "active" | "invalidated" | "closed";
  key_drivers: string[];
  risks: string[];
  disconfirming_conditions: string[];
  monitoring_metrics: string[];
  catalysts: Catalyst[];
  evidence_ids: string[];
  reviews: ThesisReview[];
  created_at: string;
  updated_at: string;
}

export interface WatchlistItem {
  ticker: string;
  thesis_ids: string[];
  monitoring_questions: string[];
  next_review_date?: string | null;
  active: boolean;
  updated_at: string;
  research_components?: Array<"management" | "risks">;
}

export interface ResearchReminder {
  reminder_id: string;
  ticker: string;
  reminder_type: "thesis_review" | "catalyst";
  title: string;
  due_date: string;
  overdue: boolean;
  thesis_id?: string | null;
  catalyst_id?: string | null;
}

export type SnapshotComponentState = "complete" | "partial" | "not_requested" | "unavailable" | "failed";

export interface SnapshotComponentResult {
  component: "financials" | "management" | "risks";
  state: SnapshotComponentState;
  reason?: string | null;
  source_count: number;
}

export interface SourceManifestEntry {
  source_id: string;
  source_type: "sec_filing" | "transcript" | "risk_report" | "other";
  provider: string;
  as_of: string;
  url?: string | null;
  metadata: Record<string, unknown>;
}

export interface CompanyResearchSnapshot {
  snapshot_id: string;
  correlation_id?: string | null;
  ticker: string;
  period: string;
  as_of: string;
  created_at: string;
  source_fingerprint: string;
  financials?: FinancialSnapshot | null;
  management?: ManagementPeriodSnapshot | null;
  risks: Array<{
    risk_id: string;
    title: string;
    status: "new" | "persistent" | "strengthened" | "weakened" | "resolved" | "unknown";
    severity?: string | null;
    evidence_ids: string[];
    attributes: Record<string, unknown>;
  }>;
  components: SnapshotComponentResult[];
  sources: SourceManifestEntry[];
  warnings: string[];
}

export interface ResearchRunManifest {
  run_id: string;
  correlation_id?: string | null;
  ticker: string;
  requested_as_of: string;
  started_at: string;
  completed_at: string;
  state: "completed" | "partial" | "failed";
  snapshot_id?: string | null;
  components: SnapshotComponentResult[];
  duration_ms: number;
  warnings: string[];
}

export interface ResearchRunResponse {
  manifest: ResearchRunManifest;
  snapshot?: CompanyResearchSnapshot | null;
}

export interface ResearchChange {
  change_id: string;
  ticker: string;
  category: "financial" | "risk" | "guidance" | "management" | "evidence";
  key: string;
  status: "new" | "persistent" | "strengthened" | "weakened" | "resolved";
  materiality: "low" | "medium" | "high" | "unknown";
  before?: unknown;
  after?: unknown;
  before_evidence_ids: string[];
  after_evidence_ids: string[];
  detection_method: string;
  explanation: string;
  confidence: number;
  analyst_review_status: "unreviewed" | "confirmed" | "ignored" | "needs_review";
}

export interface ResearchChangeSet {
  ticker: string;
  from_snapshot_id: string;
  to_snapshot_id: string;
  correlation_id?: string | null;
  generated_at: string;
  changes: ResearchChange[];
  warnings: string[];
}

export interface ResearchAlert {
  alert_id: string;
  change_id: string;
  ticker: string;
  materiality: "low" | "medium" | "high" | "unknown";
  title: string;
  explanation: string;
  status: "new" | "acknowledged" | "ignored";
  snapshot_id: string;
  correlation_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MonitorScanResponse {
  started_at: string;
  completed_at: string;
  dry_run: boolean;
  results: Array<{
    ticker: string;
    status: "completed" | "unchanged" | "partial" | "failed";
    snapshot_id?: string | null;
    new_alerts: ResearchAlert[];
    change_count: number;
    error?: string | null;
  }>;
}

export interface ExpectationPoint {
  expectation_id?: string | null;
  ticker: string;
  metric: string;
  fiscal_period: string;
  value: number;
  unit: string;
  source: string;
  origin: "user" | "csv" | "provider";
  observed_at: string;
  as_of: string;
  notes?: string | null;
}

export interface SensitivityMatrixRequest {
  ticker: string;
  kind: "growth_margin" | "margin_multiple";
  base_revenue: number;
  net_debt: number;
  diluted_shares: number;
  forecast_years: number;
  fixed_growth: number;
  fixed_margin: number;
  fixed_multiple: number;
  row_values: number[];
  column_values: number[];
  current_share_price?: number | null;
}

export interface SensitivityMatrixResponse {
  ticker: string;
  kind: "growth_margin" | "margin_multiple";
  row_label: string;
  column_label: string;
  row_values: number[];
  column_values: number[];
  cells: Array<{
    row_value: number;
    column_value: number;
    implied_share_price: number;
    upside_downside?: number | null;
  }>;
  disclaimer: string;
}

export interface PostEarningsReviewDraft {
  draft_id: string;
  ticker: string;
  thesis_id: string;
  from_snapshot_id: string;
  to_snapshot_id: string;
  generated_at: string;
  status: "draft" | "confirmed";
  locked_thesis_statement: string;
  locked_disconfirming_conditions: string[];
  locked_assumptions: Record<string, unknown>;
  changes: ResearchChange[];
  expectation_comparisons: unknown[];
  suggested_outcome: "supported" | "mixed" | "invalidated" | "unknown";
  rationale: string;
  evidence_ids: string[];
  confirmed_review_id?: string | null;
}

export interface CompanyComparisonResponse {
  as_of: string;
  period_kind: FinancialPeriodKind;
  tickers: string[];
  values: Array<{
    ticker: string;
    metric: string;
    value?: number | null;
    unit?: string | null;
    period_end?: string | null;
    source_as_of?: string | null;
    freshness_days?: number | null;
    status: "reported" | "derived" | "not_available" | "not_comparable";
    evidence_ids: string[];
    reason?: string | null;
  }>;
  warnings: string[];
  disclaimer: string;
}

export interface PeerGroup {
  peer_group_id: string;
  name: string;
  base_ticker: string;
  members: Array<{
    ticker: string;
    inclusion_reason: string;
    source: "user" | "suggested";
    confirmed_by_user: boolean;
  }>;
  industry_template: "general" | "bank" | "saas" | "semiconductor" | "energy" | "biotech";
  currency_policy: "original" | "single_currency" | "no_conversion";
  fiscal_period_policy: "latest_quarter" | "calendarized_ttm" | "latest_fy";
  user_notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PeerCandidate {
  ticker: string;
  company_name?: string | null;
  sic?: string | null;
  sic_description?: string | null;
  similarity: "same_sic" | "same_sic_division";
  inclusion_reason: string;
  confirmed_by_user: false;
}

export interface PeerAnalysisResponse {
  financials: CompanyComparisonResponse;
  risks: Array<{
    ticker: string;
    total: number;
    new: number;
    strengthened: number;
    weakened: number;
    evidence_ids: string[];
  }>;
  expectations: Array<{
    ticker: string;
    metric: string;
    fiscal_period: string;
    value: number;
    unit: string;
    source: string;
    as_of: string;
  }>;
  valuations: Array<{
    ticker: string;
    method: "pe" | "ev_ebitda" | "fcf_yield";
    status: "available" | "not_available";
    value?: number | null;
    unit: "x" | "percent";
    period: string;
    evidence_ids: string[];
  }>;
  warnings: string[];
  disclaimer: string;
}

export interface ResearchQueueResponse {
  entries: Array<{
    ticker: string;
    priority: "high" | "medium" | "low";
    reasons: string[];
    change_ids: string[];
    evidence_ids: string[];
  }>;
  disclaimer: string;
}

export interface ValuationScenarioInput {
  name: "bear" | "base" | "bull";
  annual_revenue_growth: number;
  terminal_operating_margin: number;
  ev_to_operating_income_multiple: number;
}

export interface ScenarioValuationRequest {
  ticker: string;
  currency: string;
  base_revenue: number;
  net_debt: number;
  diluted_shares: number;
  forecast_years: number;
  current_share_price?: number | null;
  scenarios: ValuationScenarioInput[];
  evidence_ids: string[];
}

export interface ScenarioValuationResponse {
  ticker: string;
  currency: string;
  forecast_years: number;
  scenarios: Array<{
    name: "bear" | "base" | "bull";
    projected_revenue: number;
    projected_operating_income: number;
    enterprise_value: number;
    equity_value: number;
    implied_share_price: number;
    upside_downside?: number | null;
    current_price_implied_terminal_margin?: number | null;
    assumptions: ValuationScenarioInput;
  }>;
  evidence_ids: string[];
  methodology: string;
  disclaimer: string;
}

export interface ManagementPeriodSnapshot {
  ticker: string;
  year: number;
  quarter: number;
  transcript_id: string;
  provider: string;
  source_url?: string | null;
  published_at?: string | null;
  overall_tone: "positive" | "neutral" | "negative" | "mixed";
  prepared_remarks_tone: "positive" | "neutral" | "negative" | "mixed" | "unclear";
  qa_tone: "positive" | "neutral" | "negative" | "mixed" | "unclear";
  uncertainty: number;
  defensiveness: number;
  guidance_signal: "raised" | "lowered" | "maintained" | "unclear";
  topic_signals: Array<{
    topic: string;
    sentiment: string;
    confidence: number;
    evidence_ids: string[];
    quotes: string[];
  }>;
  evidence_ids: string[];
}

export interface ManagementComparisonResponse {
  current: ManagementPeriodSnapshot;
  previous?: ManagementPeriodSnapshot | null;
  changes: Array<{
    dimension: string;
    previous_value: string | number;
    current_value: string | number;
    direction: "strengthened" | "weakened" | "increased" | "decreased" | "changed";
    previous_period: string;
    current_period: string;
    evidence_ids: string[];
  }>;
}

// ---------------------------------------------------------------------------
// Per-step observability types (added 2026-06-25).
// Mirrors the backend Pydantic models in src/schemas/finrisk.py.
// ---------------------------------------------------------------------------

export type RiskLifecycle = "current" | "emerging" | "receding" | "unknown";

export interface LLMCall {
  call_id: string;
  step_name: string;
  chunk_id?: string | null;
  provider: string;
  model: string;
  messages: Array<Record<string, string>>;
  prompt_text: string;
  response_text: string;
  response_structured?: Record<string, unknown> | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  latency_ms: number;
  error?: string | null;
  started_at: string;
  completed_at: string;
}

export interface ChunkValidation {
  chunk_id: string;
  pydantic_model: string;
  ok: boolean;
  errors: string[];
  validated_count: number;
  dropped_count: number;
  fallback_used?: string | null;
  section_name?: string | null;
  char_start?: number | null;
  char_end?: number | null;
  validated_at: string;
}

export interface SectionLocation {
  section_name: string;
  char_start: number;
  char_end: number;
  char_count: number;
  matched_against_real_section: boolean;
  matched_section_reason: string;
  is_disclaimer_text: boolean;
  filing_accession?: string | null;
  filing_form?: string | null;
}

export interface RiskLifecycleAnnotation {
  risk_id: string;
  lifecycle: RiskLifecycle;
  confidence: number;
  reasoning: string;
  basis: string[];
  classified_at: string;
}

export interface WorkflowLLMLogResponse {
  run_id: string;
  llm_log: LLMCall[];
}

export interface WorkflowChunksResponse {
  run_id: string;
  chunk_validations: ChunkValidation[];
}

export interface WorkflowSectionsResponse {
  run_id: string;
  section_locations: SectionLocation[];
}

export interface WorkflowLifecyclesResponse {
  run_id: string;
  risk_lifecycles: RiskLifecycleAnnotation[];
}

// ---------------------------------------------------------------------------
// V21 LLM-driven agent run types
// ---------------------------------------------------------------------------

export type AgentWorkflowKind =
  | "finrisk"
  | "supply_chain"
  | "company_research"
  | "generic_research";

export type AgentRunProvider = "deepseek" | "vllm" | "sglang";
export type AgentRunToolLoopMode = "native" | "json_fallback" | "auto";
export type AgentRunToolScope =
  | "company_research"
  | "finrisk_market"
  | "supply_chain";

export type AgentRunStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "needs_review";

export type AgentSubgoalStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "needs_review";

export interface AgentRunRequest {
  goal: string;
  workflow_kind: AgentWorkflowKind;
  provider: AgentRunProvider;
  tool_loop_mode?: AgentRunToolLoopMode | null;
  tool_scope?: AgentRunToolScope | null;
  max_tool_rounds?: number;
  model?: string | null;
  base_url?: string | null;
  demo_mode?: boolean;
  cached_mode?: boolean;
  subject?: Record<string, unknown>;
}

export interface AgentRunSummary {
  run_id: string;
  status: AgentRunStatus;
  timeline_url: string;
  trace_url: string;
}

export type RunHistoryKind = "finrisk" | "agent-runs" | "supply-chain";

export interface AgentSubgoalWire {
  subgoal_id: string;
  parent_subgoal_id?: string | null;
  objective: string;
  status: AgentSubgoalStatus;
  tool_scope: string;
  required_evidence_types: string[];
  success_criteria: string[];
  attempt_count: number;
  depends_on: string[];
}

export interface AgentDecisionWire {
  decision_id: string;
  subgoal_id?: string | null;
  decision_type: string;
  rationale: string;
  selected_tool_scope?: string | null;
  selected_tools: string[];
  stop_reason?: string | null;
  confidence: number;
  created_at: string;
}

export interface ToolExecutionEventWire {
  event_id: string;
  round_id: string;
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: "success" | "failed";
  result_summary: string;
  latency_ms: number;
  error?: string | null;
  result_chars: number;
  truncated: boolean;
  created_at: string;
}

export interface AgentEvidenceCandidateWire {
  evidence_id?: string;
  candidate_id?: string;
  kind?: string;
  status?: string;
  source_tool?: string;
  source_event_id?: string;
  source_url?: string | null;
  source_name?: string | null;
  source_title?: string | null;
  summary?: string;
  quote?: string | null;
  source_quality_score?: number;
  grounding_score?: number;
  confidence?: number;
  rejection_reason?: string | null;
  metadata?: Record<string, unknown>;
}

export interface AgentHumanReviewItemWire {
  item_id: string;
  run_id: string;
  subgoal_id?: string | null;
  object_type: string;
  object_id: string;
  reason: string;
  suggested_action: string;
  status: "pending" | "approved" | "rejected" | "commented";
  reviewer_comment?: string | null;
  created_at: string;
  reviewed_at?: string | null;
}

export interface AgentRunTimelineResponse {
  run_id: string;
  status: AgentRunStatus;
  decisions: AgentDecisionWire[];
  subgoals: AgentSubgoalWire[];
  tool_events: ToolExecutionEventWire[];
  evidence_candidates: AgentEvidenceCandidateWire[];
  human_review_items: AgentHumanReviewItemWire[];
}

export interface AgentRunTraceResponse {
  run_id: string;
  user_goal: string;
  workflow_kind: AgentWorkflowKind;
  status: AgentRunStatus;
  accepted_evidence_ids?: string[];
  fallback_events?: string[];
  budget?: Record<string, unknown>;
  tool_traces?: Array<{
    mode: AgentRunToolLoopMode;
    budget_usage?: {
      max_tool_result_chars: number;
      max_total_tool_result_chars: number;
      used_tool_result_chars: number;
      truncated_events: number;
    } | null;
    tool_events: ToolExecutionEventWire[];
  }>;
}

export interface AgentReviewActionRequest {
  action: "approve" | "reject" | "comment";
  reviewer_comment?: string | null;
}
