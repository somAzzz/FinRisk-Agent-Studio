import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { ManagementComparisonPanel } from "./ManagementComparisonPanel";

vi.mock("../api", () => ({ api: { getManagementComparison: vi.fn() } }));

describe("ManagementComparisonPanel", () => {
  beforeEach(() => {
    vi.mocked(api.getManagementComparison).mockResolvedValue({
      current: {
        ticker: "ACME", year: 2026, quarter: 1, transcript_id: "current",
        provider: "fixture", overall_tone: "positive",
        prepared_remarks_tone: "positive", qa_tone: "neutral",
        uncertainty: 0.1, defensiveness: 0.2, guidance_signal: "raised",
        topic_signals: [{ topic: "demand", sentiment: "positive", confidence: 0.5, evidence_ids: ["current:0"], quotes: ["strong demand"] }],
        evidence_ids: ["current:0"],
      },
      previous: {
        ticker: "ACME", year: 2025, quarter: 4, transcript_id: "previous",
        provider: "fixture", overall_tone: "negative",
        prepared_remarks_tone: "negative", qa_tone: "negative",
        uncertainty: 0.4, defensiveness: 0.2, guidance_signal: "lowered",
        topic_signals: [], evidence_ids: ["previous:0"],
      },
      changes: [{
        dimension: "guidance_signal", previous_value: "lowered",
        current_value: "raised", direction: "changed",
        previous_period: "2025Q4", current_period: "2026Q1",
        evidence_ids: ["previous:0", "current:0"],
      }],
    });
  });

  it("requires explicit periods and renders evidence-linked changes", async () => {
    render(<ManagementComparisonPanel ticker="ACME" />);
    fireEvent.click(screen.getByText("Management signal comparison"));
    fireEvent.click(screen.getByRole("button", { name: "Compare calls" }));
    expect(screen.getByText("Select both transcript periods before comparing.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Current transcript year"), { target: { value: "2026" } });
    fireEvent.change(screen.getByLabelText("Current transcript quarter"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Comparison transcript year"), { target: { value: "2025" } });
    fireEvent.change(screen.getByLabelText("Comparison transcript quarter"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare calls" }));
    await waitFor(() => expect(api.getManagementComparison).toHaveBeenCalledWith("ACME", 2026, 1, 2025, 4));
    expect(await screen.findByText("lowered → raised")).toBeInTheDocument();
    expect(screen.getByText("previous:0, current:0")).toBeInTheDocument();
  });
});
