import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvaluationTab } from "./EvaluationTab";
import type { WorkflowEvaluationV16 } from "../types";

const PASS: WorkflowEvaluationV16 = {
  run_id: "r-1",
  final_status: "pass",
  step_evaluations: [
    {
      step_name: "company_resolver",
      status: "pass",
      findings: [],
      latency_ms: 12,
    },
  ],
  overall_metrics: { source_diversity: 0.5, hallucination_risk: 0.1 },
  blocker_count: 0,
  warning_count: 0,
  unsupported_claims: [],
  human_review_required: false,
};

const NEEDS_REVIEW: WorkflowEvaluationV16 = {
  run_id: "r-1",
  final_status: "needs_review",
  step_evaluations: [
    {
      step_name: "graph_reasoner",
      status: "needs_review",
      findings: [
        {
          step_name: "graph_reasoner",
          check_name: "graph_path",
          status: "needs_review",
          severity: "warning",
          message: "path has hypothesis edge",
          affected_object_type: "graph_path",
          affected_object_id: "p-1",
          recommendation: "verify with a human reviewer",
        },
      ],
      latency_ms: 40,
    },
  ],
  overall_metrics: { source_diversity: 0.1 },
  blocker_count: 0,
  warning_count: 1,
  unsupported_claims: [],
  human_review_required: true,
};

describe("EvaluationTab", () => {
  it("renders empty state when no evaluation is present", () => {
    render(<EvaluationTab evaluation={null} />);
    expect(screen.getByTestId("evaluation-tab-empty")).toBeInTheDocument();
  });

  it("renders pass status and metrics", () => {
    render(<EvaluationTab evaluation={PASS} />);
    expect(screen.getByTestId("evaluation-tab-status").getAttribute("data-final-status")).toBe("pass");
    expect(screen.getByTestId("metric-blockers").textContent).toBe("0");
    expect(screen.getByTestId("metric-warnings").textContent).toBe("0");
  });

  it("renders warnings and findings drawer for needs_review", () => {
    render(<EvaluationTab evaluation={NEEDS_REVIEW} />);
    expect(screen.getByTestId("evaluation-tab-status").getAttribute("data-final-status")).toBe("needs_review");
    expect(screen.getByTestId("findings-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("finding-graph_path")).toBeInTheDocument();
  });
});
