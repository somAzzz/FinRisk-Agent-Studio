export type Entry = {
  issuer?:import("./company").Issuer;
  id: string;
  company: string;
  period: string;
  published: string | null;
  as_of: string;
  dates: string[];
  pages: number;
  status: string;
  sha256: string;
  lanes: string[];
};
export type Citation = {
  source_id: string;
  physical_page: number;
  printed_page?: string;
  quote: string;
  published_at?: string;
  extraction_method?: string;
};
export type Finding = {
  subject: string;
  topic: string;
  assessment: string;
  evidence: Citation[];
  decision: string;
  missing_data: string;
  contrary_evidence_or_test: string;
};
export type Row = { label: string; values: number[]; quote: string };
export type Fact = Row & {
  section: string;
  physical_page: number;
  printed_page?: string;
  unit: string;
  periods: string[];
};
export type Check = {
  metric: string;
  table_id: string;
  rows: Row[];
  status: string;
  physical_page: number;
  printed_page: string;
  unit: string;
  periods: string[];
  calculated: number[];
};
export type Chart = {
  metric: string;
  chart_id: string;
  unit: string;
  values: Record<string, string>;
  decimal_values: Record<string, string>;
  method: string;
  physical_page: number;
  printed_page: string;
  change: {
    from_year: string;
    to_year: string;
    value: string;
    decimal_value?: string;
    unit: string;
  };
};
export type Source = {
  source: string;
  sha256: string;
  published_at: string;
  page_count: number;
  selected_pages: number[];
  ocr_pages: number[];
};
export type Audit = {
  status: string;
  follow_up?: { missing: string; question: string };
  history: {
    proposal: { text: string; topic: string; scope: string };
    verdict: { reason: string; status: string; quote: string };
    locator?: {
      page: number;
      published: string;
      source: string;
      sha256: string;
    };
  }[];
};
export type Annual = {
  financial_rows: Fact[];
  findings: Finding[];
  reconciliations: Check[];
  chart_rows: Chart[];
  fact_reviews: Audit[];
  warnings: string[];
  unknown_topics: string[];
  decision_data_gaps: string[];
  sources: Record<string, Source>;
  supply_chain_edges: {
    from_node: string;
    relationship: string;
    to_node: string;
    fulfillment: string;
    evidence: Citation[];
  }[];
  external_events: unknown[];
  market_observations: unknown[];
  scenarios: unknown[];
  plant_decisions: unknown[];
  inline_xbrl_facts: unknown[];
};
export type CaseSource = {
  url: string;
  page?: number;
  published: string;
  anchors: string[];
  kind: string;
  sha256: string;
};
export type Link = {
  subject: string;
  relation: string;
  object: string;
  evidence: string;
  provenance: string;
  published: string;
};
export type Scenario = {
  assumptions: Record<string, string | number>;
  [key: string]: unknown;
};
export type Alert = {
  alert: string;
  day: string;
  published: string;
  product: string;
  segment: string;
  fulfillment: string;
  attributable_revenue: string;
  attributable_operating_result: string;
  evidence: string;
  financial_evidence: string;
  interpretation: string;
  actuals: Record<string, { prior: number; current: number; change: number }>;
  scenario: Scenario;
};
export type Replay = {
  edges: Link[];
  nodes: {
    id: string;
    kind: string;
    name: string;
    period?: string;
    change?: number;
    unit?: string;
  }[];
  evidence: Record<string, CaseSource>;
  alerts: Alert[];
  policies: Record<
    string,
    {
      jurisdiction: string;
      status: string;
      effective?: string;
      published: string;
      evidence: string;
    }
  >;
  policy_notes: { evidence: string; text: string }[];
  policy_task: string;
  tax_scenario: Scenario;
};
export type Fresh = {
  search_trace?: (
    | {
        query: string;
        found: string[];
        search_error: string | null;
      }
    | {
        url: string;
        decision: string;
        published?: string;
        origin?: string;
        date_evidence?: string[];
      }
  )[];
  originals?: {
    id: string;
    source: string;
    digest: string;
    published: string;
  }[];
  tasks: {
    id: string;
    topic: string;
    question: string;
    query: string;
    scope: string;
    direct_evidence_needed: string;
    state: string;
    fulfillment: string;
    action: string;
    pending?: { missing: string };
  }[];
  audits: Audit[];
  alerts: { id: string }[];
  eligible_digests: string[];
  graph: {
    nodes: {
      id: string;
      kind: string;
      source?: string;
      published?: string;
      digest?: string;
    }[];
  };
};
export type Product = {
  edges: {
    subject: string;
    object: string;
    page: number;
    quote: string;
    review: string;
    status: string;
  }[];
  methods: Record<string, number>;
  note: { page: number | null };
};
export type Bundle = {
  segment_nodes?: Record<string, string>;
  meta: Entry;
  cutoff: string;
  annual: Annual;
  original: string | null;
  fresh?: Fresh;
  reviewed?: Replay | null;
  product?: Product | null;
  narrative?: string | null;
  annual_review_available?: boolean;
};
export const pretty = (s: string) => s.replace(/_/g, " ");
export const labels: Record<string, string> = {
  Zucker: "Sugar",
  Spezialitäten: "Special products",
  Stärke: "Starch",
  Frucht: "Fruit",
  Konzern: "Group",
  Umsatzerlöse: "Revenue",
  "Operatives EBITDA": "Operating EBITDA",
  "Operatives Ergebnis": "Operating result",
  operating_result_bridge: "Operating result bridge",
  Anbaufläche: "Beet cultivation area",
  Rübenmenge: "Beet processed",
  Zuckerertrag: "Sugar yield",
  "Gesamtzuckererzeugung (einschl. Rohzuckerraffination)":
    "Total sugar output, including refining",
};
export const label = (s: string) => labels[s] || pretty(s);
export const num = (v: number) =>
  v.toLocaleString("en-GB", { maximumFractionDigits: 2 }).replace("-", "−");
export const delta = (v: number) => (v > 0 ? "+" : "") + num(v);
export const endpoint = (s: string) => s.slice(s.indexOf("/") + 1);
export const indexRoute = "#/companies/library/annual-reports";
export const reportRoute = (id: string) =>
  indexRoute + "/" + encodeURIComponent(id);
export const publicUrl = (s?: string | null) =>
  s && /^https?:\/\//i.test(s) ? s : undefined;

export async function sample<T>(file: string): Promise<T> {
  const r = await fetch(import.meta.env.BASE_URL + "annual-sample/" + file);
  if (!r.ok) throw Error("Sample file unavailable");
  return r.json();
}
