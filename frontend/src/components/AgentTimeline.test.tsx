import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentTimeline } from "./AgentTimeline";
import type { WorkflowStatusResponse } from "../types";

const STATUS: WorkflowStatusResponse = {
  run_id: "run-abc",
  status: "completed",
  trace: [
    {
      step_name: "company_resolver",
      status: "completed",
      started_at: "2026-06-20T00:00:00.000Z",
      completed_at: "2026-06-20T00:00:00.200Z",
    },
    {
      step_name: "filing_risk_extractor",
      status: "completed",
      started_at: "2026-06-20T00:00:00.300Z",
      completed_at: "2026-06-20T00:00:00.500Z",
    },
    {
      step_name: "market_explorer",
      status: "running",
      started_at: "2026-06-20T00:00:00.600Z",
    },
  ],
  company: null,
  risk_count: 0,
  evidence_count: 0,
  evaluation: null,
};

describe("AgentTimeline", () => {
  it("renders all eight steps even when trace is partial", () => {
    render(<AgentTimeline status={STATUS} />);
    expect(screen.getByTestId("step-company_resolver")).toBeInTheDocument();
    expect(screen.getByTestId("step-filing_risk_extractor")).toBeInTheDocument();
    expect(screen.getByTestId("step-market_explorer")).toBeInTheDocument();
    expect(screen.getByTestId("step-evidence_normalizer")).toBeInTheDocument();
    expect(screen.getByTestId("step-risk_scorer")).toBeInTheDocument();
    expect(screen.getByTestId("step-graph_reasoner")).toBeInTheDocument();
    expect(screen.getByTestId("step-report_generator")).toBeInTheDocument();
    expect(screen.getByTestId("step-evaluator")).toBeInTheDocument();
  });

  it("marks each step with the correct status", () => {
    render(<AgentTimeline status={STATUS} />);
    expect(
      screen.getByTestId("step-company_resolver").getAttribute("data-step-status"),
    ).toBe("completed");
    expect(
      screen.getByTestId("step-market_explorer").getAttribute("data-step-status"),
    ).toBe("running");
    // Unseen step should default to skipped.
    expect(
      screen.getByTestId("step-evaluator").getAttribute("data-step-status"),
    ).toBe("skipped");
  });
});
