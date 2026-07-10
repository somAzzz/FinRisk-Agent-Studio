import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { ResearchJournalPanel } from "./ResearchJournalPanel";

vi.mock("../api", () => ({
  api: {
    listTheses: vi.fn(),
    listWatchlist: vi.fn(),
    listResearchReminders: vi.fn(),
    saveThesis: vi.fn(),
    saveWatchlistItem: vi.fn(),
    reviewThesis: vi.fn(),
  },
}));

const thesis = {
  thesis_id: "thesis-1",
  ticker: "ACME",
  statement: "Pricing supports margin recovery.",
  time_horizon: "12 months",
  status: "active" as const,
  key_drivers: ["pricing"],
  risks: [],
  disconfirming_conditions: ["Margin declines for two quarters"],
  monitoring_metrics: ["gross_margin"],
  catalysts: [],
  evidence_ids: [],
  reviews: [],
  created_at: "2026-07-11T00:00:00Z",
  updated_at: "2026-07-11T00:00:00Z",
};

describe("ResearchJournalPanel", () => {
  beforeEach(() => {
    vi.mocked(api.listTheses).mockResolvedValue([thesis]);
    vi.mocked(api.listWatchlist).mockResolvedValue([]);
    vi.mocked(api.listResearchReminders).mockResolvedValue([]);
    vi.mocked(api.saveThesis).mockResolvedValue(thesis);
    vi.stubGlobal("crypto", { randomUUID: () => "12345678-1234-1234-1234" });
  });

  it("shows thesis and falsification conditions", async () => {
    render(<ResearchJournalPanel />);
    expect(await screen.findByText("Pricing supports margin recovery.")).toBeInTheDocument();
    expect(screen.getByText("Margin declines for two quarters")).toBeInTheDocument();
    expect(screen.getByText("Link a thesis to start the watchlist.")).toBeInTheDocument();
  });

  it("requires and saves an explicit disconfirming condition", async () => {
    render(<ResearchJournalPanel />);
    fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "NEW" } });
    fireEvent.change(screen.getByLabelText("Thesis"), { target: { value: "Demand recovers." } });
    const save = screen.getByRole("button", { name: "Save active thesis" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("What would disprove it?"), {
      target: { value: "Orders decline for two quarters" },
    });
    fireEvent.click(save);
    await waitFor(() => expect(api.saveThesis).toHaveBeenCalled());
    expect(vi.mocked(api.saveThesis).mock.calls[0][0].disconfirming_conditions).toEqual([
      "Orders decline for two quarters",
    ]);
  });

  it("surfaces overdue research reminders", async () => {
    vi.mocked(api.listResearchReminders).mockResolvedValue([
      {
        reminder_id: "review:ACME:2026-07-05",
        ticker: "ACME",
        reminder_type: "thesis_review",
        title: "Review ACME research thesis",
        due_date: "2026-07-05",
        overdue: true,
      },
    ]);
    render(<ResearchJournalPanel />);
    expect(await screen.findByText("Review ACME research thesis")).toBeInTheDocument();
    expect(screen.getByText("Overdue 2026-07-05")).toBeInTheDocument();
  });
});
