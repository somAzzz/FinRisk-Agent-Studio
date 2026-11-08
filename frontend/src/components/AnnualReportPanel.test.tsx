import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { api } from "../api";
import { AnnualReportPanel } from "./AnnualReportPanel";

it.each(["file", "url"])("analyzes a %s and displays the returned results", async mode => {
  const analyze = vi.spyOn(api, "analyzeAnnualReport").mockResolvedValue({
    identity: { cover: ["Example report"] }, status: "needs_review", sources: { annual: { page_count: 4 } },
    findings: [], reconciliations: [], warnings: ["Review chart"],
  });
  render(<AnnualReportPanel />);
  fireEvent.click(screen.getByText("Analyze an annual report"));
  const source = mode === "file" ? new File(["%PDF"], "report.pdf") : "https://example.org/report.pdf";
  if (mode === "file") {
    fireEvent.change(screen.getByLabelText("Report file"), { target: { files: [source] } });
  } else {
    fireEvent.change(screen.getByLabelText("Report source"), { target: { value: "url" } });
    fireEvent.change(screen.getByLabelText("Report URL"), { target: { value: source } });
  }
  fireEvent.submit(screen.getByRole("button", { name: "Analyze report" }).closest("form")!);
  expect(await screen.findByText("Review chart")).toBeInTheDocument();
  expect(analyze).toHaveBeenCalledWith(source, {});
  analyze.mockRestore();
});
