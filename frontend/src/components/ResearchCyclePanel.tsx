import { useEffect, useState } from "react";
import { api } from "../api";
import type {
  CompanyResearchSnapshot,
  CompanyComparisonResponse,
  ExpectationPoint,
  InvestmentThesis,
  PostEarningsReviewDraft,
  ResearchAlert,
  ResearchChangeSet,
  ResearchRunResponse,
  ResearchQueueResponse,
} from "../types";

const today = () => new Date().toISOString().slice(0, 10);
const currentQuarter = () => Math.floor(new Date().getMonth() / 3) + 1;

export function ResearchCyclePanel() {
  const [ticker, setTicker] = useState("");
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [quarter, setQuarter] = useState(String(currentQuarter()));
  const [run, setRun] = useState<ResearchRunResponse | null>(null);
  const [snapshots, setSnapshots] = useState<CompanyResearchSnapshot[]>([]);
  const [changes, setChanges] = useState<ResearchChangeSet | null>(null);
  const [alerts, setAlerts] = useState<ResearchAlert[]>([]);
  const [expectations, setExpectations] = useState<ExpectationPoint[]>([]);
  const [drafts, setDrafts] = useState<PostEarningsReviewDraft[]>([]);
  const [queue, setQueue] = useState<ResearchQueueResponse | null>(null);
  const [comparison, setComparison] = useState<CompanyComparisonResponse | null>(null);
  const [theses, setTheses] = useState<InvestmentThesis[]>([]);
  const [metric, setMetric] = useState("revenue");
  const [fiscalPeriod, setFiscalPeriod] = useState("");
  const [expectedValue, setExpectedValue] = useState("");
  const [unit, setUnit] = useState("USD");
  const [source, setSource] = useState("personal model");
  const [csv, setCsv] = useState("");
  const [comparisonMetrics, setComparisonMetrics] = useState("revenue,free_cash_flow");
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshGlobal = async () => {
    try {
      const [nextAlerts, nextDrafts, nextTheses, nextWatchlist] = await Promise.all([
        api.listResearchAlerts(),
        api.listPostEarningsDrafts(),
        api.listTheses(),
        api.listWatchlist(),
      ]);
      setAlerts(nextAlerts);
      setDrafts(nextDrafts);
      setTheses(nextTheses);
      setQueue(nextWatchlist.length
        ? await api.buildResearchQueue(nextWatchlist.map((item) => item.ticker))
        : { entries: [], disclaimer: "No Watchlist companies are available." });
    } catch {
      setError("Research cycle data could not be loaded.");
    }
  };

  useEffect(() => { void refreshGlobal(); }, []);

  const refreshTicker = async (selectedTicker = ticker) => {
    const normalized = selectedTicker.toUpperCase().trim();
    if (!normalized) return;
    try {
      const [nextSnapshots, nextExpectations] = await Promise.all([
        api.listResearchSnapshots(normalized),
        api.listExpectations(normalized),
      ]);
      setSnapshots(nextSnapshots);
      setExpectations(nextExpectations);
      if (nextSnapshots.length >= 2) {
        setChanges(await api.getResearchChanges(
          normalized,
          nextSnapshots[1].snapshot_id,
          nextSnapshots[0].snapshot_id,
        ));
      } else {
        setChanges(null);
      }
      setError(null);
    } catch {
      setError("Snapshot history or changes could not be loaded.");
    }
  };

  const startRun = async () => {
    if (!ticker.trim()) return;
    setBusy(true);
    try {
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

  const scan = async () => {
    setBusy(true);
    try {
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
    const timestamp = `${today()}T00:00:00Z`;
    try {
      await api.saveExpectation({
        ticker: ticker.toUpperCase().trim(),
        metric,
        fiscal_period: fiscalPeriod,
        value: Number(expectedValue),
        unit,
        source,
        origin: "user",
        observed_at: timestamp,
        as_of: timestamp,
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
      await api.importExpectationsCsv(csv);
      setCsv("");
      await refreshTicker();
    } catch {
      setError("CSV expectations could not be imported.");
    }
  };

  const reviewChange = async (
    changeId: string,
    status: "confirmed" | "ignored" | "needs_review",
  ) => {
    await api.reviewResearchChange(changeId, status);
    await refreshTicker();
  };

  const actOnAlert = async (alertId: string, action: "acknowledge" | "ignore") => {
    await api.actOnResearchAlert(alertId, action);
    await refreshGlobal();
  };

  const createDraft = async () => {
    const thesis = theses.find((item) => item.ticker === ticker.toUpperCase().trim());
    if (!thesis || snapshots.length < 2) return;
    try {
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
    await api.confirmPostEarningsDraft(draft.draft_id, outcome, notes);
    setReviewNotes((current) => ({ ...current, [draft.draft_id]: "" }));
    await refreshGlobal();
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
        <button className="ghost" type="button" disabled={!ticker.trim()} onClick={() => void refreshTicker()}>Load history</button>
      </div>
      {run ? <div className={`cycle-run-state ${run.manifest.state}`}><strong>{run.manifest.state}</strong><span>{run.manifest.run_id}</span>{run.manifest.components.map((item) => <small key={item.component}>{item.component}: {item.state}{item.reason ? ` · ${item.reason}` : ""}</small>)}</div> : null}
      {error ? <p className="journal-error">{error}</p> : null}

      <div className="research-cycle-grid">
        <div>
          <h3>Snapshot history</h3>
          {snapshots.map((snapshot) => <article className="cycle-record" key={snapshot.snapshot_id}><strong>{snapshot.period}</strong><span>{new Date(snapshot.as_of).toLocaleDateString()}</span><small>{snapshot.sources.length} sources · {snapshot.components.filter((item) => item.state === "complete").length}/{snapshot.components.length} complete</small></article>)}
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
        <button className="ghost" type="button" onClick={() => void saveExpectation()}>Save expectation</button>
      </div><textarea aria-label="Expectations CSV" value={csv} onChange={(event) => setCsv(event.target.value)} placeholder="ticker,metric,fiscal_period,value,unit,source,observed_at,as_of" /><button className="ghost" type="button" onClick={() => void importCsv()}>Import CSV</button><p className="muted">{expectations.length} point-in-time expectations loaded.</p></details>

      {alerts.length ? <div className="cycle-alerts"><h3>Change alerts</h3>{alerts.map((alert) => <article key={alert.alert_id}><strong>{alert.ticker} · {alert.title}</strong><span>{alert.explanation}</span><small>{alert.materiality} · {alert.status}</small>{alert.status === "new" ? <div><button className="ghost" type="button" onClick={() => void actOnAlert(alert.alert_id, "acknowledge")}>Acknowledge</button><button className="ghost danger" type="button" onClick={() => void actOnAlert(alert.alert_id, "ignore")}>Ignore</button></div> : null}</article>)}</div> : null}

      <div className="cycle-queue"><header><h3>Research queue</h3><div><input aria-label="Comparison metrics" value={comparisonMetrics} onChange={(event) => setComparisonMetrics(event.target.value)} /><button className="ghost" type="button" onClick={() => void compareWatchlist()}>Compare watchlist</button></div></header>{queue?.entries.map((entry) => <article className={entry.priority} key={entry.ticker}><strong>{entry.ticker}</strong><span>{entry.priority} review priority</span><ul>{entry.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></article>)}{queue && !queue.entries.length ? <p className="muted">No material unreviewed changes.</p> : null}{comparison ? <div className="table-scroll"><table className="research-table"><thead><tr><th>Company</th><th>Metric</th><th>Value</th><th>Status</th></tr></thead><tbody>{comparison.values.map((value) => <tr key={`${value.ticker}-${value.metric}`}><td>{value.ticker}</td><td>{value.metric}</td><td>{value.value == null ? "N/A" : `${value.value.toLocaleString()} ${value.unit ?? ""}`}</td><td>{value.status}</td></tr>)}</tbody></table><p className="report-disclaimer">{comparison.disclaimer}</p></div> : null}</div>

      <div className="cycle-reviews"><header><h3>Post-earnings review</h3><button className="ghost" type="button" disabled={snapshots.length < 2 || !theses.some((item) => item.ticker === ticker.toUpperCase().trim())} onClick={() => void createDraft()}>Generate draft</button></header>{drafts.filter((draft) => !ticker || draft.ticker === ticker.toUpperCase().trim()).map((draft) => <article key={draft.draft_id}><strong>{draft.ticker} · suggested {draft.suggested_outcome}</strong><p>{draft.rationale}</p><small>{draft.changes.length} changes · {draft.status}</small>{draft.status === "draft" ? <div><input aria-label={`Review notes for ${draft.ticker} draft`} value={reviewNotes[draft.draft_id] ?? ""} onChange={(event) => setReviewNotes((current) => ({ ...current, [draft.draft_id]: event.target.value }))} placeholder="Analyst conclusion" /><button className="ghost" type="button" onClick={() => void confirmDraft(draft, "supported")}>Supported</button><button className="ghost" type="button" onClick={() => void confirmDraft(draft, "mixed")}>Mixed</button><button className="ghost danger" type="button" onClick={() => void confirmDraft(draft, "invalidated")}>Invalidated</button></div> : null}</article>)}</div>
    </section>
  );
}
