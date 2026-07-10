import { useEffect, useState } from "react";
import { api } from "../api";
import type {
  InvestmentThesis,
  ResearchReminder,
  ThesisReview,
  WatchlistItem,
} from "../types";

const now = () => new Date().toISOString();
const id = (prefix: string) => `${prefix}-${crypto.randomUUID().slice(0, 12)}`;
const splitList = (value: string) =>
  value.split(",").map((item) => item.trim()).filter(Boolean);

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

  const refresh = async () => {
    try {
      const [nextTheses, nextWatchlist, nextReminders] = await Promise.all([
        api.listTheses(),
        api.listWatchlist(),
        api.listResearchReminders(),
      ]);
      setTheses(nextTheses);
      setWatchlist(nextWatchlist);
      setReminders(nextReminders);
      setError(null);
    } catch {
      setError("Research journal could not be loaded.");
    }
  };

  useEffect(() => { void refresh(); }, []);

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
        <label>Ticker<input value={ticker} onChange={(event) => setTicker(event.target.value)} /></label>
        <label>Thesis<textarea value={statement} onChange={(event) => setStatement(event.target.value)} /></label>
        <label>Time horizon<input value={timeHorizon} onChange={(event) => setTimeHorizon(event.target.value)} /></label>
        <label>What would disprove it?<textarea value={disconfirming} onChange={(event) => setDisconfirming(event.target.value)} placeholder="Comma-separated falsification conditions" /></label>
        <label>Key drivers<input value={drivers} onChange={(event) => setDrivers(event.target.value)} placeholder="pricing, product mix" /></label>
        <label>Metrics to monitor<input value={metrics} onChange={(event) => setMetrics(event.target.value)} placeholder="gross_margin, revenue" /></label>
        <button className="primary" type="button" disabled={busy || !ticker || !statement || !disconfirming} onClick={() => void saveThesis()}>
          Save active thesis
        </button>
        {error ? <p className="journal-error">{error}</p> : null}
      </aside>

      <main className="journal-main">
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
      </main>
    </div>
  );
}
