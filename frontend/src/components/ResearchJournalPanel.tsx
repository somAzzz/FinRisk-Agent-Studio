import { useEffect, useState } from "react";
import { api, describeApiError } from "../api";
import type {
  InvestmentThesis,
  ResearchReminder,
  ThesisReview,
  WatchlistItem,
} from "../types";
import { ResearchCyclePanel, type ResearchTask } from "./ResearchCyclePanel";

const now = () => new Date().toISOString();
const id = (prefix: string) => `${prefix}-${crypto.randomUUID().slice(0, 12)}`;
const splitList = (value: string) =>
  value.split(",").map((item) => item.trim()).filter(Boolean);
const RESEARCH_TASKS = new Set<ResearchTask>(["cycle", "valuation", "peers", "reviews"]);

function initialResearchTask(): ResearchTask {
  if (typeof window === "undefined") return "cycle";
  const requested = new URLSearchParams(window.location.search).get("task") as ResearchTask | null;
  return requested && RESEARCH_TASKS.has(requested) ? requested : "cycle";
}

export function ResearchJournalPanel() {
  const [theses, setTheses] = useState<InvestmentThesis[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [reminders, setReminders] = useState<ResearchReminder[]>([]);
  const [ticker, setTicker] = useState("");
  const [statement, setStatement] = useState("");
  const [timeHorizon, setTimeHorizon] = useState("12 months");
  const [disconfirming, setDisconfirming] = useState("");
  const [drivers, setDrivers] = useState("");
  const [metrics, setMetrics] = useState("");
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [reviewDates, setReviewDates] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTask, setActiveTask] = useState<ResearchTask>(initialResearchTask);

  const refresh = async () => {
    const [nextTheses, nextWatchlist, nextReminders] = await Promise.allSettled([
      api.listTheses(),
      api.listWatchlist(),
      api.listResearchReminders(),
    ]);
    if (nextTheses.status === "fulfilled") setTheses(nextTheses.value);
    if (nextWatchlist.status === "fulfilled") setWatchlist(nextWatchlist.value);
    if (nextReminders.status === "fulfilled") setReminders(nextReminders.value);
    const failure = [nextTheses, nextWatchlist, nextReminders].find((result) => result.status === "rejected");
    setError(failure?.status === "rejected" ? describeApiError(failure.reason, "Research journal") : null);
  };

  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("task", activeTask);
    window.history.replaceState(null, "", url);
  }, [activeTask]);

  const saveThesis = async () => {
    if (!ticker.trim() || !statement.trim() || !disconfirming.trim()) return;
    setBusy(true);
    try {
      const timestamp = now();
      await api.saveThesis({
        thesis_id: id("thesis"),
        ticker: ticker.toUpperCase().trim(),
        statement: statement.trim(),
        time_horizon: timeHorizon.trim(),
        status: "active",
        key_drivers: splitList(drivers),
        risks: [],
        disconfirming_conditions: splitList(disconfirming),
        monitoring_metrics: splitList(metrics),
        catalysts: [],
        evidence_ids: [],
        reviews: [],
        created_at: timestamp,
        updated_at: timestamp,
      });
      setStatement("");
      setDisconfirming("");
      setDrivers("");
      setMetrics("");
      await refresh();
    } catch {
      setError("Thesis could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const addToWatchlist = async (thesis: InvestmentThesis) => {
    const existing = watchlist.find((item) => item.ticker === thesis.ticker);
    const timestamp = now();
    await api.saveWatchlistItem({
      ticker: thesis.ticker,
      thesis_ids: Array.from(new Set([...(existing?.thesis_ids ?? []), thesis.thesis_id])),
      monitoring_questions: existing?.monitoring_questions ?? [],
      next_review_date: reviewDates[thesis.thesis_id] || existing?.next_review_date || null,
      active: true,
      updated_at: timestamp,
    });
    await refresh();
  };

  const review = async (
    thesis: InvestmentThesis,
    outcome: ThesisReview["outcome"],
  ) => {
    const notes = reviewNotes[thesis.thesis_id]?.trim();
    if (!notes) return;
    await api.reviewThesis(thesis.thesis_id, {
      review_id: id("review"),
      reviewed_at: now(),
      outcome,
      notes,
      evidence_ids: [],
    });
    setReviewNotes((current) => ({ ...current, [thesis.thesis_id]: "" }));
    await refresh();
  };

  return (
    <div className="journal-layout" data-testid="research-journal">
      <aside className="journal-compose section">
        <span className="research-eyebrow">Personal research memory</span>
        <h2>New thesis</h2>
        <label>Ticker<input name="thesis_ticker" autoComplete="off" spellCheck={false} value={ticker} onChange={(event) => setTicker(event.target.value)} /></label>
        <label>Thesis<textarea name="thesis_statement" autoComplete="off" value={statement} onChange={(event) => setStatement(event.target.value)} /></label>
        <label>Time horizon<input name="thesis_time_horizon" autoComplete="off" value={timeHorizon} onChange={(event) => setTimeHorizon(event.target.value)} /></label>
        <label>What would disprove it?<textarea name="thesis_disconfirming" autoComplete="off" value={disconfirming} onChange={(event) => setDisconfirming(event.target.value)} placeholder="Comma-separated falsification conditions…" /></label>
        <label>Key drivers<input name="thesis_drivers" autoComplete="off" value={drivers} onChange={(event) => setDrivers(event.target.value)} placeholder="pricing, product mix…" /></label>
        <label>Metrics to monitor<input name="thesis_metrics" autoComplete="off" spellCheck={false} value={metrics} onChange={(event) => setMetrics(event.target.value)} placeholder="gross_margin, revenue…" /></label>
        <button className="primary" type="button" disabled={busy || !ticker || !statement || !disconfirming} onClick={() => void saveThesis()}>
          Save active thesis
        </button>
        {error ? <div className="recoverable-error" role="alert"><p>{error}</p><button className="ghost" type="button" onClick={() => void refresh()}>Retry journal</button></div> : null}
      </aside>

      <main className="journal-main">
        <nav className="research-task-nav" aria-label="Research tasks">
          {(["cycle", "valuation", "peers", "reviews"] as ResearchTask[]).map((task) => <button key={task} type="button" className={activeTask === task ? "active" : ""} aria-current={activeTask === task ? "page" : undefined} onClick={() => setActiveTask(task)}>{task === "cycle" ? "Research cycle" : task === "valuation" ? "Valuation" : task === "peers" ? "Peer analysis" : "Reviews"}</button>)}
        </nav>
        <ResearchCyclePanel activeTask={activeTask} />
        {reminders.length ? (
          <section className="section reminder-ledger">
            <h2>Due research</h2>
            {reminders.map((reminder) => (
              <article className={reminder.overdue ? "overdue" : ""} key={reminder.reminder_id}>
                <strong>{reminder.ticker}</strong><span>{reminder.title}</span><small>{reminder.overdue ? "Overdue" : "Due"} {reminder.due_date}</small>
              </article>
            ))}
          </section>
        ) : null}
        <section className="section watchlist-ledger">
          <h2>Watchlist</h2>
          {watchlist.length ? watchlist.map((item) => (
            <article key={item.ticker}><strong>{item.ticker}</strong><span>{item.thesis_ids.length} linked theses</span><small>{item.next_review_date ? `Review ${item.next_review_date}` : "Review date not set"}</small></article>
          )) : <p className="muted">Link a thesis to start the watchlist.</p>}
        </section>
        <section className="section">
          <h2>Thesis ledger</h2>
          <div className="thesis-list">
            {theses.map((thesis) => (
              <article className={`thesis-card ${thesis.status}`} key={thesis.thesis_id}>
                <header><div><strong>{thesis.ticker}</strong><span>{thesis.status}</span></div><small>{thesis.time_horizon}</small></header>
                <p>{thesis.statement}</p>
                <div className="falsification-box"><b>Disconfirming conditions</b><ul>{thesis.disconfirming_conditions.map((condition) => <li key={condition}>{condition}</li>)}</ul></div>
                <div className="thesis-meta"><span>Drivers: {thesis.key_drivers.join(", ") || "—"}</span><span>Monitor: {thesis.monitoring_metrics.join(", ") || "—"}</span><span>{thesis.reviews.length} reviews</span></div>
                <div className="thesis-actions">
                  <input type="date" aria-label={`Next review date for ${thesis.ticker}`} value={reviewDates[thesis.thesis_id] ?? ""} onChange={(event) => setReviewDates((current) => ({ ...current, [thesis.thesis_id]: event.target.value }))} />
                  <button className="ghost" type="button" onClick={() => void addToWatchlist(thesis)}>Add to watchlist</button>
                  <input aria-label={`Review notes for ${thesis.ticker}`} value={reviewNotes[thesis.thesis_id] ?? ""} onChange={(event) => setReviewNotes((current) => ({ ...current, [thesis.thesis_id]: event.target.value }))} placeholder="Review evidence and outcome" />
                  <button className="ghost" type="button" onClick={() => void review(thesis, "supported")}>Supported</button>
                  <button className="ghost" type="button" onClick={() => void review(thesis, "mixed")}>Mixed</button>
                  <button className="ghost danger" type="button" onClick={() => void review(thesis, "invalidated")}>Invalidated</button>
                </div>
              </article>
            ))}
            {!theses.length ? <p className="muted">No saved thesis yet.</p> : null}
          </div>
        </section>
        <details className="section operations-boundary">
          <summary>Local data & scheduling</summary>
          <p>Database migration, backup, restore, API keys, TLS, and system schedulers remain administrator operations. Run them through the documented CLI on the host; the browser does not expose destructive database controls.</p>
        </details>
      </main>
    </div>
  );
}
