import type {
  FinancialChange,
  FinancialMetricPoint,
  FinancialPeriodKind,
  FinancialSnapshot,
} from "../types";

interface Props {
  snapshot: FinancialSnapshot | null;
  loading?: boolean;
  error?: string | null;
}

const METRICS: Array<{
  key: string;
  label: string;
  preferred: FinancialPeriodKind[];
}> = [
  { key: "revenue", label: "Revenue", preferred: ["ttm", "annual", "quarter"] },
  { key: "gross_margin", label: "Gross margin", preferred: ["ttm", "annual", "quarter"] },
  { key: "operating_margin", label: "Operating margin", preferred: ["ttm", "annual", "quarter"] },
  { key: "net_income", label: "Net income", preferred: ["ttm", "annual", "quarter"] },
  { key: "free_cash_flow", label: "Free cash flow", preferred: ["ttm", "annual", "quarter"] },
  { key: "cash", label: "Cash", preferred: ["instant"] },
  { key: "total_debt", label: "Total debt", preferred: ["instant"] },
];

function selectLatest(
  snapshot: FinancialSnapshot,
  metric: string,
  preferred: FinancialPeriodKind[],
): FinancialMetricPoint | null {
  for (const kind of preferred) {
    const candidates = snapshot.metrics
      .filter((point) => point.metric === metric && point.period_kind === kind)
      .sort((left, right) => right.period_end.localeCompare(left.period_end));
    if (candidates[0]) return candidates[0];
  }
  return null;
}

function selectChange(
  snapshot: FinancialSnapshot,
  point: FinancialMetricPoint,
): FinancialChange | null {
  const priority = ["ttm_yoy", "yoy", "annual_yoy", "qoq"];
  return (
    [...snapshot.changes]
      .filter(
        (change) =>
          change.metric === point.metric &&
          change.current_period_end === point.period_end,
      )
      .sort(
        (left, right) =>
          priority.indexOf(left.change_type) - priority.indexOf(right.change_type),
      )[0] ?? null
  );
}

function formatValue(point: FinancialMetricPoint): string {
  if (point.unit === "ratio") return `${(point.value * 100).toFixed(1)}%`;
  if (point.unit === "USD") {
    return new Intl.NumberFormat("en", {
      notation: "compact",
      maximumFractionDigits: 1,
      style: "currency",
      currency: "USD",
    }).format(point.value);
  }
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(point.value);
}

function formatChange(change: FinancialChange | null): string {
  if (!change || change.percent_change == null) return "—";
  const prefix = change.percent_change > 0 ? "+" : "";
  return `${prefix}${(change.percent_change * 100).toFixed(1)}% ${change.change_type}`;
}

function formatKpiChange(change: FinancialChange | null): string {
  if (!change || change.percent_change == null) return "No comparison";
  const prefix = change.percent_change > 0 ? "+" : "";
  return `${prefix}${(change.percent_change * 100).toFixed(1)}% vs prior`;
}

export function FinancialTrendPanel({ snapshot, loading, error }: Props) {
  if (loading) {
    return <section className="section empty-state">Loading SEC financial history…</section>;
  }
  if (error) {
    return (
      <section className="section financial-unavailable" data-testid="financial-error">
        <h2>Financial trend</h2>
        <p>{error}</p>
        <small>The risk report remains available; quantitative cross-check is incomplete.</small>
      </section>
    );
  }
  if (!snapshot) return null;

  const rows = METRICS.map((definition) => {
    const point = selectLatest(snapshot, definition.key, definition.preferred);
    return point ? { definition, point, change: selectChange(snapshot, point) } : null;
  }).filter((row): row is NonNullable<typeof row> => row !== null);

  return (
    <section className="section financial-workspace" data-testid="financial-trend-panel">
      <div className="financial-heading">
        <div>
          <span className="page-eyebrow">Point-in-time fact layer</span>
          <h2>Financial trend</h2>
          <p>Standardized SEC facts · knowledge cutoff {snapshot.as_of.slice(0, 10)}</p>
        </div>
        <span>{snapshot.ticker} · {rows.length} metrics</span>
      </div>
      <div className="financial-kpi-strip">
        {rows.slice(0, 5).map(({ definition, point, change }) => (
          <article key={definition.key}>
            <span>{point.period_kind === "ttm" ? `TTM ${definition.label}` : definition.label}</span>
            <strong>{formatValue(point)}</strong>
            <small className={change?.percent_change && change.percent_change < 0 ? "negative-change" : "positive-change"}>{formatKpiChange(change)}</small>
          </article>
        ))}
      </div>
      <div className="financial-table-heading"><div><h3>Standardized metrics</h3><p>Every value retains filing lineage and derivation status.</p></div><span>As of {snapshot.as_of.slice(0, 10)}</span></div>
      <div className="table-scroll">
        <table className="research-table financial-table">
          <thead>
            <tr><th>Metric</th><th>Latest</th><th>Period</th><th>Change</th><th>Lineage</th></tr>
          </thead>
          <tbody>
            {rows.map(({ definition, point, change }) => (
              <tr key={definition.key}>
                <td><strong>{definition.label}</strong></td>
                <td>{formatValue(point)}</td>
                <td>{point.period_end} · {point.period_kind}</td>
                <td className={change?.percent_change && change.percent_change < 0 ? "negative-change" : "positive-change"}>
                  {formatChange(change)}
                </td>
                <td>
                  <span className={`metric-status ${point.status}`}>{point.status}</span>
                  <small>{point.derivation ?? point.source_concept}</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {snapshot.warnings.length ? (
        <details className="financial-warnings">
          <summary>{snapshot.warnings.length} data coverage warnings</summary>
          <ul>{snapshot.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </details>
      ) : null}
    </section>
  );
}
