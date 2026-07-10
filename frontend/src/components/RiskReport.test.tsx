import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RiskReport } from "./RiskReport";
import reportPayload from "../../../tests/fixtures/finrisk/report_payload_contract.json";
import type { RiskReport as RiskReportType, RiskReportV16Wire } from "../types";

const FIXTURE: RiskReportType = {
  title: "Apple Inc. Risk Intelligence Brief",
  executive_summary: "Top 2 risks: supply chain and policy.",
  top_risks: [
    {
      risk_id: "risk-supply-asia",
      risk_type: "supply_chain",
      risk_factor: "Asia concentration.",
      severity: 4,
      evidence_quote: "Reliance on Asian outsourcing.",
      source: "sec_filing:0000320193",
      confidence: 0.85,
    },
    {
      risk_id: "risk-tariff",
      risk_type: "policy",
      risk_factor: "Tariff exposure.",
      severity: 3,
      evidence_quote: "Tariffs may impact gross margin.",
      source: "sec_filing:0000320193",
      confidence: 0.8,
    },
  ],
  risk_scores: [
    {
      risk_id: "risk-supply-asia",
      base_severity: 4,
      recent_signal_strength: 0.7,
      evidence_quality: 0.9,
      source_diversity: 0.6,
      novelty_score: 0.5,
      final_score: 0.62,
      score_reasoning: "deterministic",
    },
  ],
  evidence_table: [
    {
      evidence_id: "ne-risk-supply-asia",
      source_type: "filing",
      source_name: "Apple 10-K",
      source_url: null,
      quote: "Reliance on Asian outsourcing.",
      summary: "Apple discloses supply-chain concentration.",
      related_risk_ids: ["risk-supply-asia"],
    },
  ],
  graph_insights: [
    {
      insight_id: "g-tsmc-taiwan",
      source_company: "Apple Inc.",
      affected_entity: "Taiwan Strait risk",
      risk_path: ["Apple Inc.", "TSMC", "Taiwan Strait risk"],
      supporting_evidence_ids: ["ne-risk-supply-asia"],
      confidence: 0.7,
    },
  ],
  evidence_vs_inference:
    "**Evidence**: filing quote.\n**Inference**: graph path.\n**Hypothesis**: trigger.",
  limitations: "Auto-generated brief.",
  recommended_next_questions: ["Pull 8-K."],
  markdown: "# Apple Inc.",
};

describe("RiskReport", () => {
  it("renders an empty-state when no report is present", () => {
    render(<RiskReport report={null} />);
    expect(screen.getByTestId("risk-report-empty")).toBeInTheDocument();
  });

  it("renders risks, evidence, and insights for a fixture report", () => {
    render(<RiskReport report={FIXTURE} />);
    expect(screen.getByTestId("risk-risk-supply-asia")).toBeInTheDocument();
    expect(screen.getByTestId("risk-risk-tariff")).toBeInTheDocument();
    expect(screen.getByTestId("score-risk-supply-asia")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-table")).toBeInTheDocument();
    expect(screen.getByTestId("graph-insights")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-vs-inference")).toBeInTheDocument();
    expect(screen.getByTestId("limitations")).toBeInTheDocument();
    expect(screen.getByTestId("recommendations")).toBeInTheDocument();
  });

  it("renders every analyst-facing section in a v16 report", () => {
    render(
      <RiskReport
        report={null}
        reportV16={reportPayload as RiskReportV16Wire}
      />,
    );

    expect(screen.getByTestId("v16-recent-changes")).toBeInTheDocument();
    expect(screen.getByTestId("v16-evidence-table")).toBeInTheDocument();
    expect(screen.getByTestId("v16-second-order-effects")).toBeInTheDocument();
    expect(screen.getByTestId("v16-claims")).toBeInTheDocument();
    expect(screen.getByTestId("v16-financial-impacts")).toBeInTheDocument();
    expect(screen.getByTestId("v16-limitations")).toBeInTheDocument();
    expect(screen.getByTestId("v16-recommendations")).toBeInTheDocument();
  });
});
