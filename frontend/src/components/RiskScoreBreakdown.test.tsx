import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RiskScoreBreakdown } from "./RiskScoreBreakdown";
import type { RiskScore } from "../types";

const SCORES: RiskScore[] = [
  {
    risk_id: "r-1",
    base_severity: 4,
    recent_signal_strength: 0.7,
    evidence_quality: 0.8,
    source_diversity: 0.5,
    novelty_score: 0.6,
    graph_centrality: 0.4,
    final_score: 0.66,
    score_reasoning: "deterministic",
  },
];

describe("RiskScoreBreakdown", () => {
  it("renders empty state when no scores are present", () => {
    render(<RiskScoreBreakdown scores={[]} />);
    expect(screen.getByTestId("risk-score-empty")).toBeInTheDocument();
  });

  it("renders the breakdown table for a single score", () => {
    render(<RiskScoreBreakdown scores={SCORES} />);
    expect(screen.getByTestId("risk-score-breakdown")).toBeInTheDocument();
    expect(screen.getByTestId("row-r-1")).toBeInTheDocument();
    expect(screen.getByTestId("final-r-1").textContent).toContain("0.66");
  });
});
