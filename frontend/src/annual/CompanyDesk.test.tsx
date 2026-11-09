import { expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { api } from "../api";
import CompanyDesk from "./CompanyDesk";
import type { CompanyDesk as Data } from "./company";

it("keeps the issuer and ticker on both research actions and separates the two document sources", async () => {
  const id = "de-mannheim-hrb-42";
  const scope = { id, ticker: "SZU", name: "Südzucker AG" };
  const file = {
    issuer: {
      status: "confirmed",
      company_id: id,
      listings: [
        {
          symbol: "SZU",
          isin: "DE0007297004",
          qualified: "SZUG.DE",
          page: 18,
          quote: "Listing",
        },
      ],
    },
    company: scope.name,
    sha256: "sha",
    cutoff: "2026-05-21",
  };
  const data: Data = {
    id,
    name: scope.name,
    as_of: "2026-05-21",
    filings: [
      {
        ...file,
        id: "prior",
        period: "2024/25",
        published: "2025-05-15",
        original: "https://example.org/prior.pdf",
      },
      {
        ...file,
        id: "next",
        period: "2025/26",
        published: "2026-05-21",
        original: "https://example.org/next.pdf",
      },
    ],
    comparisons: [
      {
        from: "prior",
        to: "next",
        rows: [
          {
            segment: "Zucker",
            metric: "Operatives Ergebnis",
            unit: "Mio. €",
            current: -177,
            prior: -13,
            comparative: -13,
            change: -164,
            pages: [3, 6],
            quotes: ["prior row", "current row"],
            status: "comparable",
          },
        ],
      },
    ],
    questions: [],
    briefs: [],
    journal: [],
  };
  const spy = vi.spyOn(api, "companyWorkspace").mockResolvedValue(data);
  const start = vi.fn(),
    journal = vi.fn();
  render(
    <CompanyDesk
      id={id}
      day={data.as_of}
      staticMode={false}
      start={start}
      journal={journal}
      brief={() => {}}
    />,
  );
  expect(await screen.findByText("-164")).toBeVisible();
  fireEvent.click(screen.getByText("Verify"));
  expect(screen.getByRole("link", { name: /PDF p. 3/ })).toHaveAttribute(
    "href",
    "https://example.org/prior.pdf#page=3",
  );
  expect(screen.getByRole("link", { name: /PDF p. 6/ })).toHaveAttribute(
    "href",
    "https://example.org/next.pdf#page=6",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Start a company brief" }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Write a company thesis" }),
  );
  expect(start).toHaveBeenCalledWith(scope);
  expect(journal).toHaveBeenCalledWith(scope);
  expect(spy).toHaveBeenCalledWith(id, data.as_of);
  spy.mockRestore();
});
