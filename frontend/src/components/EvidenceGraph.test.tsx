import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvidenceGraph } from "./EvidenceGraph";
import type { RiskReport as RiskReportType } from "../types";

const FIXTURE: RiskReportType = {
  title: "Apple Inc.",
  executive_summary: "summary",
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
      summary: "Apple supply chain.",
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
  evidence_vs_inference: "...",
  limitations: "...",
  recommended_next_questions: ["..."],
  markdown: "...",
};

describe("EvidenceGraph", () => {
  it("renders an empty-state when no report is present", () => {
    render(<EvidenceGraph report={null} />);
    expect(screen.getByTestId("evidence-graph-empty")).toBeInTheDocument();
  });

  it("renders the canvas when risks/evidence/insights exist", () => {
    render(<EvidenceGraph report={FIXTURE} companyName="Apple Inc." />);
    expect(screen.getByTestId("evidence-graph")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-graph-canvas")).toBeInTheDocument();
  });

  it("renders empty-state when report has no graph-able content", () => {
    const empty: RiskReportType = { ...FIXTURE, top_risks: [], evidence_table: [], graph_insights: [] };
    render(<EvidenceGraph report={empty} companyName="Apple Inc." />);
    expect(screen.getByTestId("evidence-graph-empty")).toBeInTheDocument();
  });
});
