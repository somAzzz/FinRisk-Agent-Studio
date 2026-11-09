import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { api } from "../api";
import { AnnualReportPanel } from "./AnnualReportPanel";

it.each(["file", "url"])(
  "analyzes a %s and displays the returned results",
  async (mode) => {
    sessionStorage.clear();
    const analyze = vi
      .spyOn(api, "startAnnualJob")
      .mockResolvedValue({ id: "job-test", status: "queued" });
    const read = vi
      .spyOn(api, "annualJob")
      .mockResolvedValue({
        id: "job-test",
        status: "completed",
        report_id: "run-example",
      });
    render(<AnnualReportPanel />);
    if(mode==="url"){fireEvent.change(screen.getByLabelText(/Research question/),{target:{value:"Check pricing"}});fireEvent.change(screen.getByLabelText(/Evidence cutoff/),{target:{value:"2026-10-08"}}); }
    const source =
      mode === "file"
        ? new File(["%PDF"], "report.pdf")
        : "https://example.org/report.pdf";
    if (mode === "file") {
      fireEvent.change(screen.getByLabelText("Report file"), {
        target: { files: [source] },
      });
    } else {
      fireEvent.change(screen.getByLabelText("Report source"), {
        target: { value: "url" },
      });
      fireEvent.change(screen.getByLabelText("Report URL"), {
        target: { value: source },
      });
    }
    fireEvent.submit(
      screen.getByRole("button", { name: "Analyze report" }).closest("form")!,
    );
    expect(
      await screen.findByRole("link", { name: /Open saved annual report/ }),
    ).toHaveAttribute("href", "#/companies/library/annual-reports/run-example");
    read.mockRestore();
    expect(analyze).toHaveBeenCalledWith(source, mode==="url"?{as_of:"2026-10-08",goal:"Check pricing"}:{});
    analyze.mockRestore();
  },
);
