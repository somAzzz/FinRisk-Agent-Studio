import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import reportPayload from "../../../tests/fixtures/finrisk/report_payload_contract.json";
import type { RiskReportV16Wire, WorkflowEvaluation } from "../types";
import { ResearchDecisionBrief } from "./ResearchDecisionBrief";

const evaluation: WorkflowEvaluation = {
  schema_valid: true,
  has_evidence_for_each_risk: true,
  unsupported_claims: [],
  financial_advice_risk: false,
  source_diversity_score: 0.7,
  hallucination_risk_score: 0.1,
  final_status: "needs_review",
};

describe("ResearchDecisionBrief", () => {
  it("turns the v16 report into an analyst readiness summary", () => {
    render(
      <ResearchDecisionBrief
        company={null}
        report={reportPayload as RiskReportV16Wire}
        evaluation={evaluation}
      />,
    );

    expect(screen.getByTestId("research-readiness")).toHaveTextContent(
      "Analyst review required",
    );
    expect(screen.getByText("Highest-priority risk")).toBeInTheDocument();
    expect(screen.getByText("Apple diversifying to India")).toBeInTheDocument();
    expect(screen.getByText("Pull the most recent 8-K filings.")).toBeInTheDocument();
  });

  it("does not render before a v16 report exists", () => {
    const { container } = render(
      <ResearchDecisionBrief company={null} report={null} evaluation={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
