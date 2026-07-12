import { useEffect, useState } from "react";
import { api, describeApiError } from "../api";
import type {
  DiscountedCashFlowResponse,
  FinancialMetricPoint,
  FinancialSnapshot,
  MultipleValuationMethod,
  MultipleValuationResponse,
  ScenarioValuationResponse,
  SensitivityMatrixResponse,
  ValuationAssumptionSnapshot,
} from "../types";

interface Props { snapshot: FinancialSnapshot | null; }
type ScenarioName = "bear" | "base" | "bull";
type AssumptionState = Record<ScenarioName, { growth: string; margin: string; multiple: string }>;

const emptyAssumptions = (): AssumptionState => ({
  bear: { growth: "", margin: "", multiple: "" },
  base: { growth: "", margin: "", multiple: "" },
  bull: { growth: "", margin: "", multiple: "" },
});
const valuationTimestamp = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

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
  const [sensitivity, setSensitivity] = useState<SensitivityMatrixResponse | null>(null);
  const [method, setMethod] = useState<MultipleValuationMethod>("pe");
  const [period, setPeriod] = useState("TTM");
  const [earnings, setEarnings] = useState("");
  const [ebitda, setEbitda] = useState("");
  const [freeCashFlow, setFreeCashFlow] = useState("");
  const [multipleResult, setMultipleResult] = useState<MultipleValuationResponse | null>(null);
  const [forecastCashFlows, setForecastCashFlows] = useState("");
  const [wacc, setWacc] = useState("");
  const [terminalGrowth, setTerminalGrowth] = useState("");
  const [dcfResult, setDcfResult] = useState<DiscountedCashFlowResponse | null>(null);
  const [history, setHistory] = useState<ValuationAssumptionSnapshot[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
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
    setSensitivity(null);
    setMultipleResult(null);
    setDcfResult(null);
    void api.listValuationAssumptions(snapshot.ticker).then((items) => {
      setHistory(items);
      setHistoryError(null);
    }).catch((nextError: unknown) => {
      setHistoryError(describeApiError(nextError, "Valuation history"));
    });
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

  const calculateSensitivity = async () => {
    const revenue = numberOrNull(baseRevenue);
    const debt = numberOrNull(netDebt);
    const dilutedShares = numberOrNull(shares);
    const forecastYears = numberOrNull(years);
    const growth = numberOrNull(assumptions.base.growth);
    const margin = numberOrNull(assumptions.base.margin);
    const multiple = numberOrNull(assumptions.base.multiple);
    if ([revenue, debt, dilutedShares, forecastYears, growth, margin, multiple].some((value) => value == null)) {
      setError("Complete the base case before calculating sensitivity.");
      return;
    }
    try {
      setSensitivity(await api.calculateSensitivity({
        ticker: snapshot.ticker,
        kind: "growth_margin",
        base_revenue: revenue as number,
        net_debt: debt as number,
        diluted_shares: dilutedShares as number,
        forecast_years: forecastYears as number,
        fixed_growth: growth as number,
        fixed_margin: margin as number,
        fixed_multiple: multiple as number,
        row_values: [growth! - 0.05, growth!, growth! + 0.05],
        column_values: [margin! - 0.05, margin!, margin! + 0.05],
        current_share_price: numberOrNull(currentPrice),
      }));
      setError(null);
    } catch {
      setError("Sensitivity matrix could not be calculated.");
    }
  };

  const sourceIds = Array.from(new Set(snapshot.metrics.flatMap((point) => point.source_accession_numbers)));

  const refreshHistory = async () => {
    try {
      setHistory(await api.listValuationAssumptions(snapshot.ticker, 20));
      setHistoryError(null);
    } catch (nextError) {
      setHistoryError(describeApiError(nextError, "Valuation history"));
    }
  };

  const calculateMultiple = async () => {
    const sharePrice = numberOrNull(currentPrice);
    const dilutedShares = numberOrNull(shares);
    const debt = numberOrNull(netDebt);
    const denominator = method === "pe" ? numberOrNull(earnings) : method === "ev_ebitda" ? numberOrNull(ebitda) : numberOrNull(freeCashFlow);
    if (sharePrice == null || dilutedShares == null || debt == null || denominator == null || !period.trim()) {
      setError("Enter share price, diluted shares, net debt, period, and the selected method denominator.");
      return;
    }
    try {
      setMultipleResult(await api.calculateMultipleValuation({
        ticker: snapshot.ticker,
        method,
        share_price: sharePrice,
        diluted_shares: dilutedShares,
        net_debt: debt,
        earnings: method === "pe" ? denominator : null,
        ebitda: method === "ev_ebitda" ? denominator : null,
        free_cash_flow: method === "fcf_yield" ? denominator : null,
        period: period.trim(),
        evidence_ids: sourceIds,
      }));
      setError(null);
      await refreshHistory();
    } catch (nextError) {
      setError(describeApiError(nextError, "Multiple valuation"));
    }
  };

  const calculateDcf = async () => {
    const cashFlows = forecastCashFlows.split(",").map((value) => Number(value.trim())).filter(Number.isFinite);
    const discountRate = numberOrNull(wacc);
    const growth = numberOrNull(terminalGrowth);
    const debt = numberOrNull(netDebt);
    const dilutedShares = numberOrNull(shares);
    if (!cashFlows.length || discountRate == null || growth == null || debt == null || dilutedShares == null) {
      setError("Enter comma-separated forecast free cash flows, WACC, terminal growth, net debt, and diluted shares.");
      return;
    }
    if (discountRate <= growth) {
      setError("WACC must be greater than terminal growth.");
      return;
    }
    try {
      setDcfResult(await api.calculateDiscountedCashFlow({
        ticker: snapshot.ticker,
        forecast_free_cash_flows: cashFlows,
        wacc: discountRate,
        terminal_growth: growth,
        net_debt: debt,
        diluted_shares: dilutedShares,
        evidence_ids: sourceIds,
      }));
      setError(null);
      await refreshHistory();
    } catch (nextError) {
      setError(describeApiError(nextError, "DCF valuation"));
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
      <div className="valuation-actions"><button className="primary valuation-run" type="button" onClick={() => void calculate()}>Calculate user scenarios</button><button className="ghost valuation-run" type="button" onClick={() => void calculateSensitivity()}>Build sensitivity matrix</button></div>
      {error ? <p className="journal-error">{error}</p> : null}
      {result ? (
        <div className="table-scroll"><table className="research-table valuation-results"><thead><tr><th>Case</th><th>Implied/share</th><th>Vs current</th><th>Current price implies margin</th></tr></thead><tbody>
          {result.scenarios.map((scenario) => <tr key={scenario.name}><td>{scenario.name}</td><td>{new Intl.NumberFormat("en", { style: "currency", currency: result.currency }).format(scenario.implied_share_price)}</td><td>{scenario.upside_downside == null ? "—" : `${(scenario.upside_downside * 100).toFixed(1)}%`}</td><td>{scenario.current_price_implied_terminal_margin == null ? "—" : `${(scenario.current_price_implied_terminal_margin * 100).toFixed(1)}%`}</td></tr>)}
        </tbody></table><p className="report-disclaimer">{result.disclaimer}</p></div>
      ) : null}
      {sensitivity ? (
        <div className="table-scroll"><table className="research-table sensitivity-results"><thead><tr><th>{sensitivity.row_label} / {sensitivity.column_label}</th>{sensitivity.column_values.map((value) => <th key={value}>{(value * 100).toFixed(1)}%</th>)}</tr></thead><tbody>
          {sensitivity.row_values.map((row) => <tr key={row}><th>{(row * 100).toFixed(1)}%</th>{sensitivity.column_values.map((column) => { const cell = sensitivity.cells.find((item) => item.row_value === row && item.column_value === column); return <td key={column}>{cell ? new Intl.NumberFormat("en", { style: "currency", currency: snapshot.currency }).format(cell.implied_share_price) : "—"}</td>; })}</tr>)}
        </tbody></table><p className="report-disclaimer">{sensitivity.disclaimer}</p></div>
      ) : null}
      <div className="valuation-method-grid">
        <section aria-labelledby="multiple-valuation-title">
          <h3 id="multiple-valuation-title">Market multiples</h3>
          <p className="valuation-note">Market price and denominators are explicit analyst inputs. Negative or unavailable denominators remain unavailable.</p>
          <div className="valuation-baseline">
            <label>Method<select aria-label="Multiple valuation method" value={method} onChange={(event) => setMethod(event.target.value as MultipleValuationMethod)}><option value="pe">P / E</option><option value="ev_ebitda">EV / EBITDA</option><option value="fcf_yield">FCF yield</option></select></label>
            <label>Period<input aria-label="Multiple valuation period" value={period} onChange={(event) => setPeriod(event.target.value)} /></label>
            {method === "pe" ? <label>Earnings<input aria-label="Valuation earnings" value={earnings} onChange={(event) => setEarnings(event.target.value)} /></label> : null}
            {method === "ev_ebitda" ? <label>EBITDA<input aria-label="Valuation EBITDA" value={ebitda} onChange={(event) => setEbitda(event.target.value)} /></label> : null}
            {method === "fcf_yield" ? <label>Free cash flow<input aria-label="Valuation free cash flow" value={freeCashFlow} onChange={(event) => setFreeCashFlow(event.target.value)} /></label> : null}
          </div>
          <button className="ghost valuation-run" type="button" onClick={() => void calculateMultiple()}>Calculate multiple</button>
          {multipleResult ? <div className="valuation-result-card" aria-live="polite"><strong>{multipleResult.status === "available" && multipleResult.value != null ? `${multipleResult.value.toFixed(2)}${multipleResult.unit === "x" ? "x" : "%"}` : "N/A"}</strong><span>{multipleResult.method} · {multipleResult.period}</span><p>{multipleResult.reason ?? multipleResult.methodology}</p></div> : null}
        </section>
        <section aria-labelledby="dcf-valuation-title">
          <h3 id="dcf-valuation-title">Discounted cash flow</h3>
          <p className="valuation-note">Enter each forecast year explicitly. The tool does not generate cash-flow forecasts.</p>
          <div className="valuation-baseline">
            <label>Forecast FCF<input aria-label="Forecast free cash flows" placeholder="100, 110, 120" value={forecastCashFlows} onChange={(event) => setForecastCashFlows(event.target.value)} /></label>
            <label>WACC<input aria-label="DCF WACC" placeholder="0.10" value={wacc} onChange={(event) => setWacc(event.target.value)} /></label>
            <label>Terminal growth<input aria-label="DCF terminal growth" placeholder="0.03" value={terminalGrowth} onChange={(event) => setTerminalGrowth(event.target.value)} /></label>
          </div>
          <button className="ghost valuation-run" type="button" onClick={() => void calculateDcf()}>Calculate DCF</button>
          {dcfResult ? <div className="valuation-result-card" aria-live="polite"><strong>{new Intl.NumberFormat("en", { style: "currency", currency: snapshot.currency }).format(dcfResult.implied_share_price)}</strong><span>Implied value per share</span><p>{dcfResult.methodology}</p></div> : null}
        </section>
      </div>
      <details className="valuation-history"><summary>Assumption history <small>{history.length} saved runs</small></summary>
        {historyError ? <div className="recoverable-error" role="alert"><p>{historyError}</p><button className="ghost" type="button" onClick={() => void refreshHistory()}>Retry valuation history</button></div> : null}
        {history.map((item) => <article key={item.assumption_snapshot_id}><strong>{item.kind}</strong><span>{valuationTimestamp.format(new Date(item.created_at))}</span><small>{item.assumption_snapshot_id}</small></article>)}
        {!history.length && !historyError ? <p className="muted">Calculate a scenario, multiple, sensitivity matrix, or DCF to preserve its assumptions here.</p> : null}
      </details>
    </details>
  );
}
