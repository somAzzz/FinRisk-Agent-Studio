import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ClaimEvidenceMatrix, type ClaimRow } from "./ClaimEvidenceMatrix";

const CLAIMS: ClaimRow[] = [
  {
    claim_id: "c-1",
    claim_type: "evidence",
    text: "Apple depends on Asian suppliers",
    supporting_evidence_ids: ["ne-1"],
    grounding: "grounded",
    status: "pass",
    recommendation: null,
  },
  {
    claim_id: "c-2",
    claim_type: "hypothesis",
    text: "Tariffs will compress margins",
    supporting_evidence_ids: ["ne-1"],
    grounding: "needs_review",
    status: "needs_review",
    recommendation: "verify with human reviewer",
  },
];

describe("ClaimEvidenceMatrix", () => {
  it("renders empty state when no claims are present", () => {
    render(<ClaimEvidenceMatrix claims={[]} />);
    expect(screen.getByTestId("claim-matrix-empty")).toBeInTheDocument();
  });

  it("renders one row per claim", () => {
    render(<ClaimEvidenceMatrix claims={CLAIMS} />);
    expect(screen.getByTestId("claim-c-1")).toBeInTheDocument();
    expect(screen.getByTestId("claim-c-2")).toBeInTheDocument();
  });
});
