export type Listing = {
  symbol: string;
  qualified: string | null;
  isin: string;
  page: number;
  quote: string;
};
export type Issuer = {
  status: string;
  company_id: string | null;
  listings?: Listing[];
  registration?: { page: number; quote: string };
};
export type CompanyScope = { id: string; ticker: string; name: string };
export type Filing = {
  id: string;
  issuer: Issuer;
  company: string;
  period: string;
  published: string;
  sha256: string;
  original: string | null;
  cutoff: string;
};
export type Movement = {
  segment: string;
  metric: string;
  unit: string;
  prior: number | null;
  current: number | null;
  comparative: number | null;
  change: number | null;
  status: string;
  pages: number[];
  quotes: (string | null)[];
};
export type Checkpoint = {
  id: string;
  origin: string;
  kind: string;
  question: string;
  status: string;
  fulfillment: string;
  page?: number;
  quote?: string;
  required?: string;
  cutoff?: string;
  unit?: string;
  range?: number[];
  answer?: {
    value: number;
    page: number;
    report: string;
    quote: string;
    published: string;
  } | null;
  trail?: {
    published: string;
    reviewed: string;
    url?: string;
    page: number;
    digest: string;
    verdict: string;
    quote: string;
  }[];
};
export type CompanyDesk = {
  id: string;
  name: string;
  as_of: string;
  filings: Filing[];
  comparisons: { from: string; to: string; rows: Movement[] }[];
  questions: Checkpoint[];
  briefs: {
    id: string;
    ticker: string;
    title: string;
    date: string;
    summary: string;
    status: string;
  }[];
  journal: {
    id: string;
    ticker: string;
    title: string;
    date: string;
    status: string;
    conditions: string[];
  }[];
};
export const issuerRoute = (id: string, day?: string) =>
  "#/companies/" +
  encodeURIComponent(id) +
  "/dossier" +
  (day ? "?day=" + encodeURIComponent(day) : "");
