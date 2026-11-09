import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import annual from "../../../docs/reports/suedzucker-reanalysis/annual.json";
import reviewed from "../../../docs/reports/suedzucker-reanalysis/replay/2026-11-08.json";
import fresh from "../../../docs/reports/suedzucker-reanalysis/fresh-tracking/2026-11-08.json";
import discovery from "../../../docs/reports/suedzucker-reanalysis/fresh-tracking/discovery.json";
import product from "../../../docs/reports/suedzucker-reanalysis/product-audit.json";
import { api } from "../api";
import AnnualWorkspace from "./AnnualWorkspace";
import { reportRoute, type Bundle } from "./model";

afterEach(() => {
  vi.restoreAllMocks();
  history.replaceState(null, "", "#/");
});
function desk(params: string) {
  const b = {
    annual,
    reviewed,
    fresh: { ...fresh, search_trace: discovery },
    product,
    original: "https://example.org/report.pdf",
    cutoff: "2026-11-08",
    meta: {
      id: "case",
      company: "Test company",
      period: "FY",
      dates: ["2026-11-08"],
      published: "2026-05-21",
      pages: 278,
    },
    segment_nodes: { Zucker: "Segment/Sugar" },
  } as unknown as Bundle;
  history.replaceState(null, "", reportRoute("case") + "?" + params);
  vi.spyOn(api, "savedAnnual").mockResolvedValue(b);
  Element.prototype.scrollIntoView = vi.fn();
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
  return render(<AnnualWorkspace staticMode={false} start={() => {}} />);
}
it("links an accounting change to its source, then follows the actual reported H1 segment result", async () => {
  desk("view=overview");
  expect(await screen.findByText(/87.7% of the net decline/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "−164 ↗" }));
  const dialog = screen.getByRole("dialog", { name: "Source evidence" });
  expect(within(dialog).getByText(/Zucker –177 –13/)).toBeVisible();
  expect(within(dialog).getByRole("link")).toHaveAttribute(
    "href",
    "https://example.org/report.pdf#page=6",
  );
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Close evidence" }),
  );
  await screen.findByRole("button", { name: "Sugar" });
  fireEvent.click(screen.getByRole("button", { name: "Sugar" }));
  expect(screen.getByText("305,800 ha")).toBeVisible();
  expect(screen.getByText("−2.8% published change")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /View related alerts/ }));
  expect(screen.getByText("0 new · 2 carried forward")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /Trace evidence path/ }));
  expect(screen.getByText(/change of \+26 EURm/)).toHaveTextContent(
    "Attributable impact: unknown",
  );
  expect(screen.getByText("4 links in focus", { exact: false })).toBeVisible();
});
it("keeps unknown candidates out of the business hierarchy, including when search has no match", async () => {
  desk("view=relationships&layer=candidates");
  expect(
    await screen.findByText(/28 candidate relationships/),
  ).toHaveTextContent("0 confirmed");
  fireEvent.change(screen.getByLabelText("Find product or proposed segment"), {
    target: { value: "no-such-product" },
  });
  expect(screen.getByText("0 matching candidates")).toBeVisible();
  expect(screen.queryByText(/Catalogue mention/)).toBeNull();
});

it("reads the mixed acquisition log without treating source decisions as searches or alerts", async () => {
  desk("view=tracking&lane=fresh&trace=on");
  expect(await screen.findByText("0 new alerts")).toBeVisible();
  expect(
    screen.getByText("Discovery log · 3 searches · 21 source decisions"),
  ).toBeVisible();
  expect(screen.getAllByText("dated edition")).toHaveLength(2);
});

it("keeps company research bound to its filing and restores the original analysis selection after refresh", async () => {
  const params =
    "view=relationships&day=2026-11-08&layer=candidates&search=BENEO";
  const initial = desk(params);
  await screen.findByRole("heading", { name: "Test company" });
  expect(
    screen.getAllByRole("navigation", { name: /workspace sections/ }),
  ).toHaveLength(1);
  const jump =
    reportRoute("case") +
    "?" +
    new URLSearchParams({
      workspace: "company",
      day: "2026-11-08",
      from: params,
    });
  // Mount from the linked URL, as for opening in another tab.
  initial.unmount();
  history.replaceState(null, "", jump);
  const work = render(<AnnualWorkspace staticMode={false} start={() => {}} />);
  await screen.findByRole("heading", { name: "Test company" });
  const tabs = screen.getByRole("navigation", {
    name: "Test company workspace sections",
  });
  fireEvent.click(within(tabs).getByRole("button", { name: "Financials" }));
  expect(screen.getByText("305,800 ha")).toBeVisible();
  expect(within(tabs).queryByRole("button", { name: "Management" })).toBeNull();
  work.unmount();
  render(<AnnualWorkspace staticMode={false} start={() => {}} />);
  expect(
    await screen.findByRole("link", { name: /Return to annual report/ }),
  ).toHaveAttribute("href", reportRoute("case") + "?" + params);
  expect(screen.queryByText(/Apple Inc\./)).toBeNull();
});

it("opens a draft from a real tracking question without running or resolving it", async () => {
  const start = vi.spyOn(api, "startAgentRun");
  desk("view=tracking&lane=fresh");
  fireEvent.click(
    (
      await screen.findAllByRole("button", { name: "Inspect task and search" })
    )[0],
  );
  fireEvent.click(
    screen.getByRole("button", { name: /Investigate this question/ }),
  );
  expect(await screen.findByTestId("agent-goal-input")).toHaveValue(
    fresh.tasks[0].question,
  );
  expect(screen.getByText(/New results belong to Research Runs/)).toBeVisible();
  expect(start).not.toHaveBeenCalled();
});
