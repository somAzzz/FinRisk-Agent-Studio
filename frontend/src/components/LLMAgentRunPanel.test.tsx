import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { LLMAgentRunPanel } from "./LLMAgentRunPanel";

const startAgentRunMock = vi.fn().mockResolvedValue({
  run_id: "agent-abc",
  status: "completed",
  timeline_url: "/agent-runs/agent-abc/timeline",
  trace_url: "/agent-runs/agent-abc/trace.json",
});

const getTimelineMock = vi.fn().mockResolvedValue({
  run_id: "agent-abc",
  status: "completed",
  decisions: [],
  subgoals: [
    {
      subgoal_id: "sg-1",
      objective: "Find supply chain evidence",
      status: "completed",
      tool_scope: "finrisk_market",
      required_evidence_types: ["filing", "web"],
      success_criteria: ["cite sources"],
      attempt_count: 1,
      depends_on: [],
    },
  ],
  tool_events: [
    {
      event_id: "tool-1",
      round_id: "round-0",
      tool_call_id: "call-1",
      tool_name: "graph_path_search",
      arguments: { source_entity: "AAPL" },
      status: "success",
      result_summary: JSON.stringify({
        data: {
          graph_source: "unavailable",
          paths: [],
          error: "Graph backend unavailable",
        },
      }),
      latency_ms: 12,
      error: null,
      result_chars: 140,
      truncated: false,
      created_at: "2026-06-27T00:00:00.000Z",
    },
    {
      event_id: "tool-2",
      round_id: "round-1",
      tool_call_id: "call-2",
      tool_name: "browser_explore",
      arguments: { goal: "inspect", timeout_seconds: 0.1 },
      status: "failed",
      result_summary: JSON.stringify({
        data: {
          browser_backend: "playwright",
          timed_out: true,
          error: "browser_explore timed out after 0.1s",
        },
      }),
      latency_ms: 100,
      error: "tool result budget exhausted",
      result_chars: 120,
      truncated: true,
      created_at: "2026-06-27T00:00:01.000Z",
    },
    {
      event_id: "tool-3",
      round_id: "round-2",
      tool_call_id: "call-3",
      tool_name: "web_search",
      arguments: { query: "Apple supply chain" },
      status: "success",
      result_summary: JSON.stringify({
        data: {
          results: [
            {
              url: "https://www.sec.gov/example",
              metadata: {
                source_quality_score: 3.75,
                source_quality_reason: "preferred_domain",
              },
            },
          ],
        },
      }),
      latency_ms: 80,
      error: null,
      result_chars: 180,
      truncated: false,
      created_at: "2026-06-27T00:00:02.000Z",
    },
  ],
  evidence_candidates: [
    {
      evidence_id: "ev-1",
      kind: "filing",
      status: "accepted",
      source_url: "https://www.sec.gov/example",
      source_name: "SEC",
      summary: "Apple discusses supplier concentration.",
      source_quality_score: 0.95,
      grounding_score: 0.8,
    },
    {
      candidate_id: "evcand-review",
      kind: "web",
      status: "needs_review",
      source_url: "https://example.com/source",
      source_title: "Example Source",
      source_event_id: "tool-3",
      summary: "This evidence needs a human decision.",
      source_quality_score: 0.6,
      grounding_score: 0.1,
      rejection_reason: "grounding below threshold (0.10)",
    },
  ],
  human_review_items: [
    {
      item_id: "hri-1",
      run_id: "agent-abc",
      object_type: "evidence_candidate",
      object_id: "ev-2",
      reason: "Source needs inspection",
      suggested_action: "inspect_source",
      status: "pending",
      created_at: "2026-06-27T00:00:03.000Z",
    },
  ],
});

const getTraceMock = vi.fn().mockResolvedValue({
  run_id: "agent-abc",
  user_goal: "Find evidence",
  workflow_kind: "finrisk",
  status: "completed",
  accepted_evidence_ids: ["ev-1"],
  fallback_events: ["graph_builder:Neo4j client unavailable"],
  tool_traces: [
    {
      mode: "native",
      budget_usage: {
        max_tool_result_chars: 12000,
        max_total_tool_result_chars: 40000,
        used_tool_result_chars: 3021,
        truncated_events: 1,
      },
      tool_events: [],
    },
  ],
});

const reviewMock = vi.fn().mockResolvedValue({
  item_id: "hri-1",
  run_id: "agent-abc",
  object_type: "evidence_candidate",
  object_id: "ev-2",
  reason: "Source needs inspection",
  suggested_action: "inspect_source",
  status: "approved",
  created_at: "2026-06-27T00:00:03.000Z",
});
const reviewCandidateMock = vi.fn().mockResolvedValue({
  candidate_id: "evcand-review",
  status: "accepted",
});

vi.mock("../api", () => ({
  api: {
    startAgentRun: (...args: unknown[]) => startAgentRunMock(...args),
    getAgentRunTimeline: (...args: unknown[]) => getTimelineMock(...args),
    getAgentRunTrace: (...args: unknown[]) => getTraceMock(...args),
    reviewAgentRunItem: (...args: unknown[]) => reviewMock(...args),
    reviewAgentRunCandidate: (...args: unknown[]) => reviewCandidateMock(...args),
  },
}));

describe("LLMAgentRunPanel", () => {
  beforeEach(() => {
    startAgentRunMock.mockClear();
    getTimelineMock.mockClear();
    getTraceMock.mockClear();
    reviewMock.mockClear();
    reviewCandidateMock.mockClear();
  });

  it("starts a V21 agent run and renders backend trace metadata", async () => {
    render(<LLMAgentRunPanel />);

    fireEvent.click(screen.getByTestId("agent-run-button"));

    await waitFor(() => {
      expect(screen.getByTestId("agent-status")).toHaveTextContent("completed");
    });

    expect(startAgentRunMock).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: "deepseek",
        tool_scope: "finrisk_market",
      }),
    );
    expect(screen.getByTestId("agent-budget")).toHaveTextContent("3021/40000");
    expect(screen.getByTestId("agent-subgoal-sg-1")).toHaveTextContent(
      "Find supply chain evidence",
    );
    expect(screen.getByTestId("tool-event-graph_path_search")).toHaveTextContent(
      "graph: unavailable",
    );
    expect(screen.getByTestId("tool-event-browser_explore")).toHaveTextContent(
      "browser timed out",
    );
    expect(screen.getByTestId("tool-event-web_search")).toHaveTextContent(
      "quality 3.75",
    );
    expect(screen.getByTestId("tool-event-web_search")).toHaveTextContent(
      "Searched: Apple supply chain",
    );
    expect(screen.queryByText(/\"results\"/)).not.toBeInTheDocument();
    expect(screen.getByTestId("agent-evidence-graph")).toBeInTheDocument();
    expect(screen.getAllByTestId("agent-evidence-candidate")[0]).toHaveTextContent(
      "Apple discusses supplier concentration",
    );
    expect(screen.getAllByText("Example Source").length).toBeGreaterThan(0);
  });

  it("approves pending review items", async () => {
    render(<LLMAgentRunPanel />);

    fireEvent.click(screen.getByTestId("agent-run-button"));
    await screen.findByText("Source needs inspection");
    const reviewCard = screen.getByText("Source needs inspection").closest("article");
    expect(reviewCard).not.toBeNull();
    fireEvent.click(
      within(reviewCard as HTMLElement).getByRole("button", { name: /approve/i }),
    );

    await waitFor(() => {
      expect(reviewMock).toHaveBeenCalledWith("agent-abc", "hri-1", {
        action: "approve",
      });
    });
  });

  it("approves needs-review evidence candidates directly", async () => {
    render(<LLMAgentRunPanel />);

    fireEvent.click(screen.getByTestId("agent-run-button"));
    await screen.findByText("This evidence needs a human decision.");
    const candidateCard = screen
      .getByText("This evidence needs a human decision.")
      .closest("article");
    expect(candidateCard).not.toBeNull();
    fireEvent.click(
      within(candidateCard as HTMLElement).getByRole("button", {
        name: /approve/i,
      }),
    );

    await waitFor(() => {
      expect(reviewCandidateMock).toHaveBeenCalledWith(
        "agent-abc",
        "evcand-review",
        { action: "approve" },
      );
    });
  });
});
