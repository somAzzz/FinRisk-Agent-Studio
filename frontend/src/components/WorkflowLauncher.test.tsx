import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { WorkflowLauncher } from "./WorkflowLauncher";
import type { WorkflowRunSummary } from "../types";

vi.mock("../api", () => ({
  api: {
    startWorkflow: vi.fn(),
  },
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
  it("renders default AAPL form", () => {
    render(<WorkflowLauncher onStarted={() => {}} busy={false} />);
    const ticker = screen.getByTestId("ticker-input") as HTMLInputElement;
    expect(ticker.value).toBe("AAPL");
    expect(screen.getByTestId("demo-mode")).toBeChecked();
  });

  it("submits the request and invokes onStarted", async () => {
    (api.startWorkflow as ReturnType<typeof vi.fn>).mockResolvedValue(SUMMARY);
    const onStarted = vi.fn();
    render(<WorkflowLauncher onStarted={onStarted} busy={false} />);
    fireEvent.click(screen.getByTestId("run-button"));
    await waitFor(() => {
      expect(api.startWorkflow).toHaveBeenCalled();
    });
    expect(onStarted).toHaveBeenCalledWith(
      SUMMARY,
      expect.objectContaining({ ticker: "AAPL", demo_mode: true }),
    );
  });

  it("surfaces API errors", async () => {
    (api.startWorkflow as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("network down"),
    );
    render(<WorkflowLauncher onStarted={() => {}} busy={false} />);
    fireEvent.click(screen.getByTestId("run-button"));
    await waitFor(() => {
      expect(screen.getByTestId("launcher-error").textContent).toMatch(
        /network down/,
      );
    });
  });
});
