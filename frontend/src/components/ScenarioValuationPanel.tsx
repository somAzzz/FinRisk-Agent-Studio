import { useEffect, useState } from "react";
import { api } from "../api";
import type {
  FinancialMetricPoint,
  FinancialSnapshot,
  ScenarioValuationResponse,
} from "../types";

interface Props { snapshot: FinancialSnapshot | null; }
type ScenarioName = "bear" | "base" | "bull";
type AssumptionState = Record<ScenarioName, { growth: string; margin: string; multiple: string }>;

const emptyAssumptions = (): AssumptionState => ({
  bear: { growth: "", margin: "", multiple: "" },
  base: { growth: "", margin: "", multiple: "" },
  bull: { growth: "", margin: "", multiple: "" },
});

function latest(snapshot: FinancialSnapshot, metric: string): FinancialMetricPoint | null {
  return [...snapshot.metrics]
    .filter((point) => point.metric === metric)
    .sort((left, right) => right.period_end.localeCompare(left.period_end))[0] ?? null;
}

function numberOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function ScenarioValuationPanel({ snapshot }: Props) {
  const [baseRevenue, setBaseRevenue] = useState("");
  const [netDebt, setNetDebt] = useState("");
  const [shares, setShares] = useState("");
  const [currentPrice, setCurrentPrice] = useState("");
  const [years, setYears] = useState("2");
  const [assumptions, setAssumptions] = useState<AssumptionState>(emptyAssumptions);
  const [result, setResult] = useState<ScenarioValuationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!snapshot) return;
    const revenue = latest(snapshot, "revenue");
    const debt = latest(snapshot, "total_debt");
    const cash = latest(snapshot, "cash");
    const dilutedShares = latest(snapshot, "diluted_shares");
    setBaseRevenue(revenue ? String(revenue.value) : "");
    setNetDebt(debt && cash ? String(debt.value - cash.value) : "");
    setShares(dilutedShares ? String(dilutedShares.value) : "");
    setResult(null);
  }, [snapshot]);

  if (!snapshot) return null;

  const update = (name: ScenarioName, key: "growth" | "margin" | "multiple", value: string) => {
    setAssumptions((current) => ({
      ...current,
      [name]: { ...current[name], [key]: value },
    }));
  };

  const calculate = async () => {
    const revenue = numberOrNull(baseRevenue);
    const debt = numberOrNull(netDebt);
    const dilutedShares = numberOrNull(shares);
    const forecastYears = numberOrNull(years);
    const scenarioRows = (["bear", "base", "bull"] as ScenarioName[]).map((name) => ({
      name,
      annual_revenue_growth: numberOrNull(assumptions[name].growth),
      terminal_operating_margin: numberOrNull(assumptions[name].margin),
      ev_to_operating_income_multiple: numberOrNull(assumptions[name].multiple),
    }));
    if (revenue == null || debt == null || dilutedShares == null || forecastYears == null ||
        scenarioRows.some((row) => Object.values(row).some((value) => value == null))) {
      setError("Complete every assumption before calculating scenarios.");
      return;
    }
    const sourceIds = Array.from(new Set(snapshot.metrics.flatMap((point) => point.source_accession_numbers)));
    try {
      setResult(await api.calculateValuation({
        ticker: snapshot.ticker,
        currency: snapshot.currency,
        base_revenue: revenue,
        net_debt: debt,
        diluted_shares: dilutedShares,
        forecast_years: forecastYears,
        current_share_price: numberOrNull(currentPrice),
        scenarios: scenarioRows.map((row) => ({
          name: row.name,
          annual_revenue_growth: row.annual_revenue_growth as number,
          terminal_operating_margin: row.terminal_operating_margin as number,
          ev_to_operating_income_multiple: row.ev_to_operating_income_multiple as number,
        })),
        evidence_ids: sourceIds,
      }));
      setError(null);
    } catch {
      setError("Scenario valuation could not be calculated.");
    }
  };

  return (
    <details className="section valuation-panel" data-testid="valuation-panel">
      <summary><span>Scenario valuation</span><small>User assumptions · no price target</small></summary>
      <p className="valuation-note">SEC-derived baselines are prefilled where available. Growth, margin, multiple and market price remain your assumptions.</p>
      <div className="valuation-baseline">
        <label>Base revenue<input aria-label="Base revenue" value={baseRevenue} onChange={(event) => setBaseRevenue(event.target.value)} /></label>
        <label>Net debt<input aria-label="Net debt" value={netDebt} onChange={(event) => setNetDebt(event.target.value)} /></label>
        <label>Diluted shares<input aria-label="Diluted shares" value={shares} onChange={(event) => setShares(event.target.value)} /></label>
        <label>Current share price<input aria-label="Current share price" value={currentPrice} onChange={(event) => setCurrentPrice(event.target.value)} /></label>
        <label>Forecast years<input aria-label="Forecast years" value={years} onChange={(event) => setYears(event.target.value)} /></label>
      </div>
      <div className="valuation-assumptions">
        {(["bear", "base", "bull"] as ScenarioName[]).map((name) => (
          <fieldset key={name}><legend>{name}</legend>
            <label>Annual growth<input aria-label={`${name} annual growth`} placeholder="e.g. 0.05" value={assumptions[name].growth} onChange={(event) => update(name, "growth", event.target.value)} /></label>
            <label>Terminal margin<input aria-label={`${name} terminal margin`} placeholder="e.g. 0.20" value={assumptions[name].margin} onChange={(event) => update(name, "margin", event.target.value)} /></label>
            <label>EV / operating income<input aria-label={`${name} multiple`} placeholder="e.g. 15" value={assumptions[name].multiple} onChange={(event) => update(name, "multiple", event.target.value)} /></label>
          </fieldset>
        ))}
      </div>
      <button className="primary valuation-run" type="button" onClick={() => void calculate()}>Calculate user scenarios</button>
      {error ? <p className="journal-error">{error}</p> : null}
      {result ? (
        <div className="table-scroll"><table className="research-table valuation-results"><thead><tr><th>Case</th><th>Implied/share</th><th>Vs current</th><th>Current price implies margin</th></tr></thead><tbody>
          {result.scenarios.map((scenario) => <tr key={scenario.name}><td>{scenario.name}</td><td>{new Intl.NumberFormat("en", { style: "currency", currency: result.currency }).format(scenario.implied_share_price)}</td><td>{scenario.upside_downside == null ? "—" : `${(scenario.upside_downside * 100).toFixed(1)}%`}</td><td>{scenario.current_price_implied_terminal_margin == null ? "—" : `${(scenario.current_price_implied_terminal_margin * 100).toFixed(1)}%`}</td></tr>)}
        </tbody></table><p className="report-disclaimer">{result.disclaimer}</p></div>
      ) : null}
    </details>
  );
}
