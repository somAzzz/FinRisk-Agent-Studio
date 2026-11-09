import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { WorkflowLauncher } from "./WorkflowLauncher";
import type { WorkflowRunSummary } from "../types";

vi.mock("../api", () => ({
  api: {
    startWorkflow: vi.fn(),
  },
  describeApiError: (error: Error) => error.message,
  FinRiskApiError: class extends Error {
    status: number;
    body: unknown;
    constructor(message: string, status: number, body: unknown) {
      super(message);
      this.status = status;
      this.body = body;
    }
  },
}));

import { api } from "../api";

const SUMMARY: WorkflowRunSummary = {
  run_id: "run-test",
  status: "queued",
  started_at: "2026-06-20T00:00:00.000Z",
  report_url: "/workflows/run-test/report",
};

describe("WorkflowLauncher", () => {
  it("starts with no assumed company or runtime settings", () => {
    render(<WorkflowLauncher onStarted={() => {}} busy={false} />);
    const ticker = screen.getByTestId("ticker-input") as HTMLInputElement;
    expect(ticker.value).toBe("");
    expect(screen.queryByTestId("demo-mode")).toBeNull();
    expect(screen.queryByTestId("llm-provider-select")).toBeNull();
  });

  it("submits the request and invokes onStarted", async () => {
    (api.startWorkflow as ReturnType<typeof vi.fn>).mockResolvedValue(SUMMARY);
    const onStarted = vi.fn();
    render(<WorkflowLauncher onStarted={onStarted} busy={false} />);
    fireEvent.change(screen.getByTestId("ticker-input"),{target:{value:"ACME"}});
    fireEvent.click(screen.getByTestId("run-button"));
    await waitFor(() => {
      expect(api.startWorkflow).toHaveBeenCalled();
    });
    expect(onStarted).toHaveBeenCalledWith(
      SUMMARY,
      expect.objectContaining({
        ticker: "ACME",
      }),
    );
  });

  it("submits the selected time horizon range", async () => {
    (api.startWorkflow as ReturnType<typeof vi.fn>).mockResolvedValue(SUMMARY);
    render(<WorkflowLauncher onStarted={() => {}} busy={false} />);
    fireEvent.change(screen.getByTestId("horizon-start"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByTestId("horizon-end"), {
      target: { value: "18" },
    });
    expect(screen.getByTestId("horizon-value").textContent).toBe("3-18 months");
    fireEvent.change(screen.getByTestId("ticker-input"),{target:{value:"ACME"}});
    fireEvent.click(screen.getByTestId("run-button"));
    await waitFor(() => {
      expect(api.startWorkflow).toHaveBeenCalledWith(
        expect.objectContaining({
          time_horizon: "3-18 months",
        }),
      );
    });
  });

  it("requires at least one evidence source and leaves deployment to the server", async () => {
    render(<WorkflowLauncher initialTicker="ACME" onStarted={()=>{}} busy={false}/>);
    for(const src of ["filing","graph","web"]) fireEvent.click(screen.getByTestId("source-"+src));
    expect(screen.getByTestId("run-button")).toBeDisabled();
    fireEvent.click(screen.getByTestId("source-filing"));
    fireEvent.click(screen.getByTestId("run-button"));
    await waitFor(()=>expect(api.startWorkflow).toHaveBeenLastCalledWith({ticker:"ACME", company_name:undefined,analysis_goal:expect.any(String),time_horizon:"6-12 months",sources:["filing"]}));
  });

  it("surfaces API errors", async () => {
    (api.startWorkflow as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("network down"),
    );
    render(<WorkflowLauncher onStarted={() => {}} busy={false} />);
    fireEvent.change(screen.getByTestId("ticker-input"),{target:{value:"ACME"}});
    fireEvent.click(screen.getByTestId("run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("launcher-error").textContent).toMatch(
        /network down/,
      );
    });
  });
});
