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
    expect(screen.getByTestId("llm-provider-select")).toHaveValue("sglang");
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
      expect.objectContaining({
        ticker: "AAPL",
        demo_mode: true,
        llm_config: expect.objectContaining({ provider: "sglang" }),
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
    fireEvent.click(screen.getByTestId("run-button"));
    await waitFor(() => {
      expect(api.startWorkflow).toHaveBeenCalledWith(
        expect.objectContaining({
          time_horizon: "3-18 months",
        }),
      );
    });
  });

  it("submits the selected LLM provider", async () => {
    (api.startWorkflow as ReturnType<typeof vi.fn>).mockResolvedValue(SUMMARY);
    render(<WorkflowLauncher onStarted={() => {}} busy={false} />);
    fireEvent.change(screen.getByTestId("llm-provider-select"), {
      target: { value: "openai" },
    });
    fireEvent.click(screen.getByTestId("run-button"));
    await waitFor(() => {
      expect(api.startWorkflow).toHaveBeenCalledWith(
        expect.objectContaining({
          llm_config: expect.objectContaining({
            provider: "openai",
            base_url: "https://api.openai.com/v1",
            model: "gpt-4o-mini",
          }),
        }),
      );
    });
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
