import graphPayloadJson from "../../tests/fixtures/finrisk/graph_payload_contract.json";
import reportPayloadJson from "../../tests/fixtures/finrisk/report_payload_contract.json";
import type {
  RiskReportV16Wire,
  WorkflowEvaluationResponse,
  WorkflowGraphResponse,
  WorkflowReportResponse,
  WorkflowRunSummary,
  WorkflowStatusResponse,
  WorkflowTraceEvent,
} from "./types";

const graphPayload = graphPayloadJson as WorkflowGraphResponse;
const reportPayload = reportPayloadJson as RiskReportV16Wire;

const RUN_ID = "static-aapl-demo";
const STARTED_AT = "2026-07-08T07:30:00.000Z";
const COMPLETED_AT = "2026-07-08T07:30:18.000Z";

const trace: WorkflowTraceEvent[] = [
  "company_resolver",
  "filing_risk_extractor",
  "market_explorer",
  "evidence_normalizer",
  "risk_scorer",
  "graph_reasoner",
  "report_generator",
  "evaluator",
].map((stepName, index) => ({
  step_name: stepName,
  status: "completed",
  started_at: new Date(Date.parse(STARTED_AT) + index * 2000).toISOString(),
  completed_at: new Date(Date.parse(STARTED_AT) + index * 2000 + 1200).toISOString(),
}));

export const staticDemoSummary: WorkflowRunSummary = {
  run_id: RUN_ID,
  status: "completed",
  current_step: null,
  started_at: STARTED_AT,
  completed_at: COMPLETED_AT,
  report_url: `/workflows/${RUN_ID}/report`,
};

export const staticDemoStatus: WorkflowStatusResponse = {
  run_id: RUN_ID,
  status: "completed",
  current_step: null,
  trace,
  company: {
    company_name: "Apple Inc.",
    ticker: "AAPL",
    cik: "0000320193",
    filing_type: "10-K",
    analysis_year: 2024,
    source: "offline fixture",
    resolved_at: STARTED_AT,
  },
  risk_count: reportPayload.top_risks.length,
  evidence_count: reportPayload.evidence_table.length,
  evaluation: {
    schema_valid: true,
    has_evidence_for_each_risk: true,
    unsupported_claims: [],
    financial_advice_risk: false,
    source_diversity_score: 0.74,
    hallucination_risk_score: 0.12,
    final_status: "needs_review",
  },
  completed_at: COMPLETED_AT,
};

export const staticDemoReport: WorkflowReportResponse = {
  run_id: RUN_ID,
  status: "completed",
  report: null,
  report_v16: reportPayload,
  markdown: reportPayload.markdown,
  evaluation: staticDemoStatus.evaluation,
};

export const staticDemoGraph = graphPayload;

export const staticDemoEvaluation: WorkflowEvaluationResponse = {
  run_id: RUN_ID,
  final_status: "needs_review",
  step_evaluations: [
    {
      step_name: "filing_risk_extractor",
      status: "warning",
      findings: [
        {
          finding_id: "static-filing-coverage",
          step_name: "filing_risk_extractor",
          check_name: "evidence_coverage",
          status: "warning",
          severity: "warning",
          message: "Static demo uses a compact SEC fixture; expand coverage before production use.",
          affected_object_type: "filing_section",
          affected_object_id: "item_1a",
          recommendation: "Review the full 10-K and recent 8-K filings.",
        },
      ],
      metrics: { extracted_risks: reportPayload.top_risks.length },
      latency_ms: 420,
      fallback_used: "offline_fixture",
    },
    {
      step_name: "graph_reasoner",
      status: "needs_review",
      findings: graphPayload.guardrail_findings,
      metrics: {
        candidate_paths: graphPayload.paths.length,
        bound_evidence: graphPayload.paths.reduce(
          (count, path) => count + path.evidence_ids.length,
          0,
        ),
      },
      latency_ms: 610,
      fallback_used: "fixture_graph",
    },
    {
      step_name: "report_generator",
      status: "pass",
      findings: [],
      metrics: { top_risks: reportPayload.top_risks.length },
      latency_ms: 380,
      fallback_used: "template_renderer",
    },
  ],
  overall_metrics: {
    evidence_coverage: 1,
    source_quality: 0.9,
    graph_path_confidence: 0.78,
  },
  blocker_count: 0,
  warning_count: 2,
  unsupported_claims: [],
  human_review_required: true,
};

export function isStaticDemoMode(): boolean {
  return import.meta.env.VITE_STATIC_DEMO === "1";
}
