import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvaluationPanel } from "./EvaluationPanel";
import type { WorkflowEvaluation } from "../types";

const PASS: WorkflowEvaluation = {
  schema_valid: true,
  has_evidence_for_each_risk: true,
  unsupported_claims: [],
  financial_advice_risk: false,
  source_diversity_score: 0.5,
  hallucination_risk_score: 0.1,
  final_status: "pass",
};

const FAIL: WorkflowEvaluation = {
  schema_valid: false,
  has_evidence_for_each_risk: false,
  unsupported_claims: ["r-orphan"],
  financial_advice_risk: true,
  source_diversity_score: 0.1,
  hallucination_risk_score: 0.9,
  final_status: "fail",
};

describe("EvaluationPanel", () => {
  it("renders an empty-state when no evaluation is present", () => {
    render(<EvaluationPanel evaluation={null} />);
    expect(screen.getByTestId("evaluation-empty")).toBeInTheDocument();
  });

  it("renders pass verdict with metrics", () => {
    render(<EvaluationPanel evaluation={PASS} />);
    expect(screen.getByTestId("evaluation-status").getAttribute("data-final-status")).toBe("pass");
    expect(screen.getByTestId("metric-diversity").textContent).toBe("0.50");
  });

  it("renders fail verdict with unsupported claims list", () => {
    render(<EvaluationPanel evaluation={FAIL} />);
    expect(screen.getByTestId("evaluation-status").getAttribute("data-final-status")).toBe("fail");
    expect(screen.getByTestId("metric-unsupported").textContent).toBe("1");
  });
});
