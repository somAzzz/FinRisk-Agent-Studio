import { useEffect, useState } from "react";
import { api, describeApiError } from "../api";
import type {
  CompanyResearchSnapshot,
  CompanyComparisonResponse,
  ExpectationPoint,
  ExpectationComparison,
  InvestmentThesis,
  LLMRunConfig,
  PostEarningsReviewDraft,
  ResearchAlert,
  ResearchChangeSet,
  ResearchRunResponse,
  ResearchQueueResponse,
  WorkflowRunSummary,
} from "../types";
import { PeerAnalysisPanel } from "./PeerAnalysisPanel";
import { ScenarioValuationPanel } from "./ScenarioValuationPanel";
import { LLMProviderSelector } from "./LLMProviderSelector";
import {
  staticResearchChanges,
  staticResearchQueue,
  staticResearchSnapshots,
  staticResearchThesis,
} from "../productDemo";

const today = () => new Date().toISOString().slice(0, 10);
const currentQuarter = () => Math.floor(new Date().getMonth() / 3) + 1;
const wait = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));
const researchDate = new Intl.DateTimeFormat("en-US", { dateStyle: "medium" });

export type ResearchTask = "cycle" | "valuation" | "peers" | "reviews";

export function ResearchCyclePanel({
  activeTask = "cycle",
  researchRevision = 0,
  staticMode = false,
}: { activeTask?: ResearchTask; researchRevision?: number; staticMode?: boolean }) {
  const [ticker, setTicker] = useState(staticMode ? "AAPL" : "");
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [quarter, setQuarter] = useState(String(currentQuarter()));
  const [run, setRun] = useState<ResearchRunResponse | null>(null);
  const [snapshots, setSnapshots] = useState<CompanyResearchSnapshot[]>(staticMode ? staticResearchSnapshots : []);
  const [changes, setChanges] = useState<ResearchChangeSet | null>(staticMode ? staticResearchChanges : null);
  const [alerts, setAlerts] = useState<ResearchAlert[]>([]);
  const [expectations, setExpectations] = useState<ExpectationPoint[]>([]);
  const [expectationComparisons, setExpectationComparisons] = useState<Record<string, ExpectationComparison>>({});
  const [drafts, setDrafts] = useState<PostEarningsReviewDraft[]>([]);
  const [queue, setQueue] = useState<ResearchQueueResponse | null>(staticMode ? staticResearchQueue : null);
  const [comparison, setComparison] = useState<CompanyComparisonResponse | null>(null);
  const [theses, setTheses] = useState<InvestmentThesis[]>(staticMode ? [staticResearchThesis] : []);
  const [metric, setMetric] = useState("revenue");
  const [fiscalPeriod, setFiscalPeriod] = useState("");
  const [expectedValue, setExpectedValue] = useState("");
  const [unit, setUnit] = useState("USD");
  const [source, setSource] = useState("personal model");
  const [expectationObservedAt, setExpectationObservedAt] = useState(today());
  const [expectationAsOf, setExpectationAsOf] = useState(today());
  const [csv, setCsv] = useState("");
  const [comparisonMetrics, setComparisonMetrics] = useState("revenue,free_cash_flow");
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowRunSummary | null>(null);
  const [analysisGoal, setAnalysisGoal] = useState("Update the evidence-linked company risk assessment.");
  const [llmConfig, setLlmConfig] = useState<LLMRunConfig>({
    provider: "vllm",
    base_url: "http://localhost:30000/v1",
    model: "nvidia/Qwen3.6-27B-NVFP4",
  });

  const refreshGlobal = async () => {
    if (staticMode) {
      setTheses([staticResearchThesis]);
      setQueue(staticResearchQueue);
      setError(null);
      return;
    }
    const [nextAlerts, nextDrafts, nextTheses, nextWatchlist] = await Promise.allSettled([
      api.listResearchAlerts(), api.listPostEarningsDrafts(), api.listTheses(), api.listWatchlist(),
    ]);
    if (nextAlerts.status === "fulfilled") setAlerts(nextAlerts.value);
    if (nextDrafts.status === "fulfilled") setDrafts(nextDrafts.value);
    if (nextTheses.status === "fulfilled") setTheses(nextTheses.value);
    if (nextWatchlist.status === "fulfilled") {
      const watchlist = nextWatchlist.value;
      try {
        setQueue(watchlist.length
          ? await api.buildResearchQueue(watchlist.map((item) => item.ticker))
          : { entries: [], disclaimer: "No Watchlist companies are available." });
      } catch (nextError) {
        setError(describeApiError(nextError, "Research queue"));
        return;
      }
    }
    const failure = [nextAlerts, nextDrafts, nextTheses, nextWatchlist].find((result) => result.status === "rejected");
    setError(failure?.status === "rejected" ? describeApiError(failure.reason, "Research cycle data") : null);
  };

  useEffect(() => { void refreshGlobal(); }, []);
  useEffect(() => {
    if (researchRevision > 0) void refreshGlobal();
  }, [researchRevision]);

  const refreshTicker = async (selectedTicker = ticker) => {
    const normalized = selectedTicker.toUpperCase().trim();
    if (!normalized) return;
    if (staticMode) {
      setSnapshots(staticResearchSnapshots);
      setChanges(staticResearchChanges);
      setError(null);
      return;
    }
    const [nextSnapshots, nextExpectations] = await Promise.allSettled([
      api.listResearchSnapshots(normalized), api.listExpectations(normalized),
    ]);
    if (nextExpectations.status === "fulfilled") setExpectations(nextExpectations.value);
    if (nextSnapshots.status === "fulfilled") {
      setSnapshots(nextSnapshots.value);
      if (nextSnapshots.value.length >= 2) {
        try {
          setChanges(await api.getResearchChanges(normalized, nextSnapshots.value[1].snapshot_id, nextSnapshots.value[0].snapshot_id));
        } catch (nextError) {
          setError(describeApiError(nextError, "Research changes"));
          return;
        }
      } else setChanges(null);
    }
    const failure = [nextSnapshots, nextExpectations].find((result) => result.status === "rejected");
    setError(failure?.status === "rejected" ? describeApiError(failure.reason, "Snapshot history") : null);
  };

  const startRun = async () => {
    if (!ticker.trim()) return;
    setBusy(true);
    try {
      if (staticMode) {
        setRun({
          manifest: {
            run_id: "research-aapl-fixture",
            ticker: "AAPL",
            requested_as_of: staticResearchSnapshots[0].as_of,
            started_at: staticResearchSnapshots[0].created_at,
            completed_at: staticResearchSnapshots[0].created_at,
            state: "completed",
            snapshot_id: staticResearchSnapshots[0].snapshot_id,
            components: staticResearchSnapshots[0].components,
            duration_ms: 840,
            warnings: [],
          },
          snapshot: staticResearchSnapshots[0],
        });
        setSnapshots(staticResearchSnapshots);
        setChanges(staticResearchChanges);
        setError(null);
        return;
      }
      const response = await api.startResearchRun({
        ticker: ticker.toUpperCase().trim(),
        year: Number(year),
        quarter: Number(quarter),
        include_management: true,
        include_risks: true,
      });
      setRun(response);
      await refreshTicker(ticker);
    } catch {
      setError("Research snapshot could not be created.");
    } finally {
      setBusy(false);
    }
  };

  const startFullCycle = async () => {
    const normalized = ticker.toUpperCase().trim();
    if (!normalized || !analysisGoal.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (staticMode) {
        setWorkflow({ run_id: "static-aapl-demo", status: "completed", current_step: null, started_at: staticResearchSnapshots[0].created_at, completed_at: staticResearchSnapshots[0].created_at, report_url: "/workflows/static-aapl-demo/report" });
        setRun({
          manifest: { run_id: "research-aapl-fixture", ticker: "AAPL", requested_as_of: staticResearchSnapshots[0].as_of, started_at: staticResearchSnapshots[0].created_at, completed_at: staticResearchSnapshots[0].created_at, state: "completed", snapshot_id: staticResearchSnapshots[0].snapshot_id, components: staticResearchSnapshots[0].components, duration_ms: 840, warnings: [] },
          snapshot: staticResearchSnapshots[0],
        });
        setSnapshots(staticResearchSnapshots);
        setChanges(staticResearchChanges);
        return;
      }
      let next = await api.startWorkflow({
        ticker: normalized,
        analysis_goal: analysisGoal.trim(),
        year: Number(year),
        sources: ["filing", "web", "transcript", "graph"],
        demo_mode: false,
        cached_mode: false,
        llm_config: llmConfig,
      });
      setWorkflow(next);
      for (let attempt = 0; attempt < 300; attempt += 1) {
        if (["completed", "needs_review", "failed"].includes(next.status)) break;
        await wait(1000);
        const status = await api.getStatus(next.run_id);
        next = {
          run_id: status.run_id,
          status: status.status,
          current_step: status.current_step,
          started_at: next.started_at,
          completed_at: status.completed_at,
          report_url: next.report_url,
        };
        setWorkflow(next);
      }
      if (next.status === "failed") throw new Error("FinRisk workflow failed");
      if (!["completed", "needs_review"].includes(next.status)) {
        throw new Error("FinRisk workflow timed out");
      }
      const response = await api.startResearchRun({
        ticker: normalized,
        year: Number(year),
        quarter: Number(quarter),
        include_management: true,
        include_risks: true,
        workflow_run_id: next.run_id,
        correlation_id: next.run_id,
      });
      setRun(response);
      await refreshTicker(normalized);
    } catch {
      setError("FinRisk workflow or linked research snapshot could not be completed.");
    } finally {
      setBusy(false);
    }
  };

  const scan = async () => {
    setBusy(true);
    try {
      if (staticMode) {
        setQueue(staticResearchQueue);
        setError(null);
        return;
      }
      await api.scanWatchlist({ minimum_materiality: "medium", max_workers: 2 });
      await refreshGlobal();
      if (ticker) await refreshTicker();
    } catch {
      setError("Watchlist scan could not be completed.");
    } finally {
      setBusy(false);
    }
  };

  const saveExpectation = async () => {
    if (!ticker || !fiscalPeriod || !expectedValue || !source) return;
    if (!expectationObservedAt || !expectationAsOf || expectationAsOf < expectationObservedAt) {
      setError("Expectation as-of date must be on or after the observed date.");
      return;
    }
    const observedAt = `${expectationObservedAt}T00:00:00Z`;
    const asOf = `${expectationAsOf}T00:00:00Z`;
    try {
      if (staticMode) {
        setExpectations((current) => [{ expectation_id: `fixture-${Date.now()}`, ticker: ticker.toUpperCase().trim(), metric, fiscal_period: fiscalPeriod, value: Number(expectedValue), unit, source, origin: "user", observed_at: observedAt, as_of: asOf }, ...current]);
        setExpectedValue("");
        setError(null);
        return;
      }
      await api.saveExpectation({
        ticker: ticker.toUpperCase().trim(),
        metric,
        fiscal_period: fiscalPeriod,
        value: Number(expectedValue),
        unit,
        source,
        origin: "user",
        observed_at: observedAt,
        as_of: asOf,
      });
      setExpectedValue("");
      await refreshTicker();
    } catch {
      setError("Expectation could not be saved.");
    }
  };

  const importCsv = async () => {
    if (!csv.trim()) return;
    try {
      if (staticMode) {
        setCsv("");
        setError(null);
        return;
      }
      await api.importExpectationsCsv(csv);
      setCsv("");
      await refreshTicker();
    } catch {
      setError("CSV expectations could not be imported.");
    }
  };

  const compareExpectation = async (point: ExpectationPoint) => {
    if (!point.expectation_id || !snapshots[0]) return;
    try {
      if (staticMode) {
        const actual = snapshots[0].financials?.metrics.find((item) => item.metric === point.metric) ?? snapshots[0].financials?.metrics[0];
        if (!actual) return;
        const absoluteSurprise = actual.value - point.value;
        setExpectationComparisons((current) => ({ ...current, [point.expectation_id as string]: { expectation: point, actual, absolute_surprise: absoluteSurprise, percent_surprise: point.value ? absoluteSurprise / point.value : null } }));
        setError(null);
        return;
      }
      const next = await api.compareExpectation(point.expectation_id, snapshots[0].snapshot_id);
      setExpectationComparisons((current) => ({ ...current, [point.expectation_id as string]: next }));
      setError(null);
    } catch (nextError) {
      setError(describeApiError(nextError, "Expectation comparison"));
    }
  };

  const reviewChange = async (
    changeId: string,
    status: "confirmed" | "ignored" | "needs_review",
  ) => {
    if (staticMode) {
      setChanges((current) => current ? { ...current, changes: current.changes.map((change) => change.change_id === changeId ? { ...change, analyst_review_status: status } : change) } : current);
      return;
    }
    await api.reviewResearchChange(changeId, status);
    await refreshTicker();
  };

  const actOnAlert = async (alertId: string, action: "acknowledge" | "ignore") => {
    if (staticMode) {
      setAlerts((current) => current.map((alert) => alert.alert_id === alertId ? { ...alert, status: action === "acknowledge" ? "acknowledged" : "ignored" } : alert));
      return;
    }
    await api.actOnResearchAlert(alertId, action);
    await refreshGlobal();
  };

  const createDraft = async () => {
    const thesis = theses.find((item) => item.ticker === ticker.toUpperCase().trim());
    if (!thesis || snapshots.length < 2) return;
    try {
      if (staticMode) {
        setDrafts((current) => current.length ? current : [{
          draft_id: "fixture-post-earnings-review",
          ticker: thesis.ticker,
          thesis_id: thesis.thesis_id,
          from_snapshot_id: snapshots[1].snapshot_id,
          to_snapshot_id: snapshots[0].snapshot_id,
          generated_at: snapshots[0].created_at,
          status: "draft",
          locked_thesis_statement: thesis.statement,
          locked_disconfirming_conditions: thesis.disconfirming_conditions,
          locked_assumptions: {},
          changes: staticResearchChanges.changes,
          expectation_comparisons: [],
          suggested_outcome: "mixed",
          rationale: "Services resilience remains supportive, while supply-chain concentration increased and needs analyst review.",
          evidence_ids: ["10-K-2025", "sc-ev-5"],
          confirmed_review_id: null,
        }]);
        setError(null);
        return;
      }
      await api.createPostEarningsDraft({
        thesis_id: thesis.thesis_id,
        from_snapshot_id: snapshots[1].snapshot_id,
        to_snapshot_id: snapshots[0].snapshot_id,
        expectation_ids: expectations.flatMap((item) => item.expectation_id ? [item.expectation_id] : []),
        locked_assumptions: {},
      });
      await refreshGlobal();
    } catch {
      setError("Post-earnings review draft could not be generated.");
    }
  };

  const compareWatchlist = async () => {
    try {
      if (staticMode) {
        setComparison({
          as_of: staticResearchSnapshots[0].as_of,
          period_kind: "ttm",
          tickers: ["AAPL"],
          values: staticResearchSnapshots[0].financials?.metrics.filter((item) => comparisonMetrics.includes(item.metric)).map((item) => ({ ticker: "AAPL", metric: item.metric, value: item.value, unit: item.unit, period_end: item.period_end, source_as_of: staticResearchSnapshots[0].as_of, freshness_days: 0, status: item.status, evidence_ids: item.source_accession_numbers })) ?? [],
          warnings: ["Add another Watchlist company for a cross-company comparison."],
          disclaimer: "Offline fixture; analyst review only.",
        });
        setError(null);
        return;
      }
      const watchlist = await api.listWatchlist();
      const histories = await Promise.all(
        watchlist.map((item) => api.listResearchSnapshots(item.ticker)),
      );
      const latest = histories.flatMap((items) => items.length ? [items[0]] : []);
      if (latest.length < 2) {
        setError("At least two Watchlist companies need snapshots for comparison.");
        return;
      }
      setComparison(await api.compareCompanies({
        snapshot_ids: latest.map((item) => item.snapshot_id),
        metrics: comparisonMetrics.split(",").map((item) => item.trim()).filter(Boolean),
        period_kind: "ttm",
      }));
      setError(null);
    } catch {
      setError("Watchlist companies are not comparable at the same as-of date.");
    }
  };

  const confirmDraft = async (
    draft: PostEarningsReviewDraft,
    outcome: "supported" | "mixed" | "invalidated",
  ) => {
    const notes = reviewNotes[draft.draft_id]?.trim();
    if (!notes) return;
    if (staticMode) setDrafts((current) => current.map((item) => item.draft_id === draft.draft_id ? { ...item, status: "confirmed", suggested_outcome: outcome } : item));
    else await api.confirmPostEarningsDraft(draft.draft_id, outcome, notes);
    setReviewNotes((current) => ({ ...current, [draft.draft_id]: "" }));
    if (!staticMode) await refreshGlobal();
  };

  return (
    <section className="section research-cycle" data-testid="research-cycle">
      <header className="research-cycle-heading">
        <div><span className="research-eyebrow">Point-in-time workflow</span><h2>Research cycle</h2></div>
        <button className="ghost" type="button" disabled={busy} onClick={() => void scan()}>Scan watchlist</button>
      </header>
      <div className="research-cycle-controls">
        <label>Ticker<input aria-label="Research cycle ticker" value={ticker} onChange={(event) => setTicker(event.target.value)} /></label>
        <label>Year<input aria-label="Research cycle year" type="number" value={year} onChange={(event) => setYear(event.target.value)} /></label>
        <label>Quarter<select aria-label="Research cycle quarter" value={quarter} onChange={(event) => setQuarter(event.target.value)}>{[1, 2, 3, 4].map((item) => <option key={item} value={item}>Q{item}</option>)}</select></label>
        <button className="primary" type="button" disabled={busy || !ticker.trim()} onClick={() => void startRun()}>Create snapshot</button>
        <button className="primary" type="button" disabled={busy || !ticker.trim() || !analysisGoal.trim()} onClick={() => void startFullCycle()}>Run FinRisk + snapshot</button>
        <button className="ghost" type="button" disabled={!ticker.trim()} onClick={() => void refreshTicker()}>Load history</button>
      </div>
      <label className="cycle-full-run-goal">FinRisk analysis goal<input aria-label="FinRisk analysis goal" value={analysisGoal} onChange={(event) => setAnalysisGoal(event.target.value)} /><small>Estimated providers: SEC filing, web search, transcript and graph. Actual requests depend on availability.</small></label>
      <details className="cycle-details cycle-llm-config"><summary>Research LLM</summary><LLMProviderSelector value={llmConfig} onChange={setLlmConfig} /></details>
      {workflow ? <div className={`cycle-run-state ${workflow.status}`}><strong>FinRisk: {workflow.status}</strong><span>{workflow.run_id}</span>{workflow.current_step ? <small>{workflow.current_step}</small> : null}</div> : null}
      {run ? <div className={`cycle-run-state ${run.manifest.state}`}><strong>{run.manifest.state}</strong><span>{run.manifest.run_id}</span>{run.manifest.components.map((item) => <small key={item.component}>{item.component}: {item.state}{item.reason ? ` · ${item.reason}` : ""}</small>)}</div> : null}
      {error ? <div className="recoverable-error" role="alert"><p>{error}</p><button className="ghost" type="button" onClick={() => void refreshGlobal()}>Retry research data</button></div> : null}

      {activeTask === "cycle" ? <>
      <div className="research-cycle-grid">
        <div>
          <h3>Snapshot history</h3>
          {snapshots.map((snapshot) => <article className="cycle-record" key={snapshot.snapshot_id}><strong>{snapshot.period}</strong><span>{researchDate.format(new Date(snapshot.as_of))}</span><small>{snapshot.sources.length} sources · {snapshot.components.filter((item) => item.state === "complete").length}/{snapshot.components.length} complete</small></article>)}
          {!snapshots.length ? <p className="muted">Load a ticker or create its first snapshot.</p> : null}
        </div>
        <div>
          <h3>Material changes</h3>
          {changes?.changes.map((change) => <article className={`cycle-change ${change.materiality}`} key={change.change_id}><header><strong>{change.key}</strong><span>{change.materiality}</span></header><p>{change.explanation}</p><small>{change.category} · {change.status} · {change.after_evidence_ids.length} current evidence</small><div><button className="ghost" type="button" onClick={() => void reviewChange(change.change_id, "confirmed")}>Confirm</button><button className="ghost" type="button" onClick={() => void reviewChange(change.change_id, "needs_review")}>Review</button><button className="ghost danger" type="button" onClick={() => void reviewChange(change.change_id, "ignored")}>Ignore</button></div></article>)}
          {changes && !changes.changes.length ? <p className="muted">No evidence-linked changes between these snapshots.</p> : null}
        </div>
      </div>

      <details className="cycle-details"><summary>Expectations and CSV import</summary><div className="expectation-form">
        <input aria-label="Expectation metric" value={metric} onChange={(event) => setMetric(event.target.value)} placeholder="metric" />
        <input aria-label="Expectation fiscal period" value={fiscalPeriod} onChange={(event) => setFiscalPeriod(event.target.value)} placeholder="2026Q1" />
        <input aria-label="Expectation value" type="number" value={expectedValue} onChange={(event) => setExpectedValue(event.target.value)} placeholder="value" />
        <input aria-label="Expectation unit" value={unit} onChange={(event) => setUnit(event.target.value)} />
        <input aria-label="Expectation source" value={source} onChange={(event) => setSource(event.target.value)} />
        <input aria-label="Expectation observed date" type="date" value={expectationObservedAt} onChange={(event) => setExpectationObservedAt(event.target.value)} />
        <input aria-label="Expectation as-of date" type="date" value={expectationAsOf} min={expectationObservedAt} onChange={(event) => setExpectationAsOf(event.target.value)} />
        <button className="ghost" type="button" onClick={() => void saveExpectation()}>Save expectation</button>
      </div><textarea aria-label="Expectations CSV" name="expectations_csv" autoComplete="off" value={csv} onChange={(event) => setCsv(event.target.value)} placeholder="ticker,metric,fiscal_period,value,unit,source,observed_at,as_of…" /><button className="ghost" type="button" onClick={() => void importCsv()}>Import CSV</button><p className="muted">{expectations.length} point-in-time expectations loaded.</p>
      {expectations.map((point) => { const comparison = point.expectation_id ? expectationComparisons[point.expectation_id] : null; return <article className="expectation-record" key={point.expectation_id ?? `${point.metric}-${point.as_of}`}><div><strong>{point.metric} · {point.fiscal_period}</strong><span>{new Intl.NumberFormat().format(point.value)} {point.unit} · {point.source}</span></div>{point.expectation_id && snapshots[0] ? <button className="ghost" type="button" onClick={() => void compareExpectation(point)}>Compare actual</button> : null}{comparison ? <p aria-live="polite"><b>{comparison.percent_surprise == null ? new Intl.NumberFormat().format(comparison.absolute_surprise) : `${new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 1 }).format(comparison.percent_surprise)} surprise`}</b> · actual {new Intl.NumberFormat().format(comparison.actual.value)} {comparison.actual.unit}</p> : null}</article>; })}
      </details>

      {alerts.length ? <div className="cycle-alerts"><h3>Change alerts</h3>{alerts.map((alert) => <article key={alert.alert_id}><strong>{alert.ticker} · {alert.title}</strong><span>{alert.explanation}</span><small>{alert.materiality} · {alert.status}</small>{alert.status === "new" ? <div><button className="ghost" type="button" onClick={() => void actOnAlert(alert.alert_id, "acknowledge")}>Acknowledge</button><button className="ghost danger" type="button" onClick={() => void actOnAlert(alert.alert_id, "ignore")}>Ignore</button></div> : null}</article>)}</div> : null}

      <div className="cycle-queue"><header><h3>Research queue</h3><div><input aria-label="Comparison metrics" value={comparisonMetrics} onChange={(event) => setComparisonMetrics(event.target.value)} /><button className="ghost" type="button" onClick={() => void compareWatchlist()}>Compare watchlist</button></div></header>{queue?.entries.map((entry) => <article className={entry.priority} key={entry.ticker}><strong>{entry.ticker}</strong><span>{entry.priority} review priority</span><ul>{entry.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></article>)}{queue && !queue.entries.length ? <p className="muted">No material unreviewed changes.</p> : null}{comparison ? <div className="table-scroll"><table className="research-table"><thead><tr><th>Company</th><th>Metric</th><th>Value</th><th>Status</th></tr></thead><tbody>{comparison.values.map((value) => <tr key={`${value.ticker}-${value.metric}`}><td>{value.ticker}</td><td>{value.metric}</td><td>{value.value == null ? "N/A" : `${value.value.toLocaleString()} ${value.unit ?? ""}`}</td><td>{value.status}</td></tr>)}</tbody></table><p className="report-disclaimer">{comparison.disclaimer}</p></div> : null}</div>
      </> : null}

      {activeTask === "valuation" ? <div className="research-task-panel"><h3>Valuation lab</h3>{snapshots[0]?.financials ? <ScenarioValuationPanel snapshot={snapshots[0].financials} /> : <p className="muted">Load or create a company snapshot with financial data to calculate valuation.</p>}</div> : null}
      {activeTask === "reviews" ? <div className="cycle-reviews"><header><h3>Post-earnings review</h3><button className="ghost" type="button" disabled={snapshots.length < 2 || !theses.some((item) => item.ticker === ticker.toUpperCase().trim())} onClick={() => void createDraft()}>Generate draft</button></header>{drafts.filter((draft) => !ticker || draft.ticker === ticker.toUpperCase().trim()).map((draft) => <article key={draft.draft_id}><strong>{draft.ticker} · suggested {draft.suggested_outcome}</strong><p>{draft.rationale}</p><small>{draft.changes.length} changes · {draft.status}</small>{draft.status === "draft" ? <div><input aria-label={`Review notes for ${draft.ticker} draft`} value={reviewNotes[draft.draft_id] ?? ""} onChange={(event) => setReviewNotes((current) => ({ ...current, [draft.draft_id]: event.target.value }))} placeholder="Analyst conclusion" /><button className="ghost" type="button" onClick={() => void confirmDraft(draft, "supported")}>Supported</button><button className="ghost" type="button" onClick={() => void confirmDraft(draft, "mixed")}>Mixed</button><button className="ghost danger" type="button" onClick={() => void confirmDraft(draft, "invalidated")}>Invalidated</button></div> : null}</article>)}</div> : null}
      {activeTask === "peers" ? <PeerAnalysisPanel staticMode={staticMode} /> : null}
    </section>
  );
}
