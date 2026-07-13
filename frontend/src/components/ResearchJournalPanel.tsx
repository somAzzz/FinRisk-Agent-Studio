import { useEffect, useState } from "react";
import { CalendarClock, ChevronDown, Plus, Target } from "lucide-react";
import { api, describeApiError } from "../api";
import type {
  InvestmentThesis,
  ResearchReminder,
  ThesisReview,
  WatchlistItem,
} from "../types";
import {
  staticResearchReminder,
  staticResearchThesis,
  staticResearchWatchlist,
} from "../productDemo";
import { ResearchCyclePanel, type ResearchTask } from "./ResearchCyclePanel";

const now = () => new Date().toISOString();
const id = (prefix: string) => `${prefix}-${crypto.randomUUID().slice(0, 12)}`;
const displayDate = (value: string | null | undefined) => value
  ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(new Date(`${value}T00:00:00Z`))
  : "Not scheduled";
const splitList = (value: string) =>
  value.split(",").map((item) => item.trim()).filter(Boolean);
const RESEARCH_TASKS = new Set<ResearchTask>(["cycle", "valuation", "peers", "reviews"]);

function initialResearchTask(): ResearchTask {
  if (typeof window === "undefined") return "cycle";
  const requested = new URLSearchParams(window.location.search).get("task") as ResearchTask | null;
  return requested && RESEARCH_TASKS.has(requested) ? requested : "cycle";
}

export function ResearchJournalPanel({ staticMode = false }: { staticMode?: boolean }) {
  const [theses, setTheses] = useState<InvestmentThesis[]>(staticMode ? [staticResearchThesis] : []);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>(staticMode ? [staticResearchWatchlist] : []);
  const [reminders, setReminders] = useState<ResearchReminder[]>(staticMode ? [staticResearchReminder] : []);
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
  const [researchRevision, setResearchRevision] = useState(0);
  const [composerOpen, setComposerOpen] = useState(!staticMode);
  const activeThesis = theses.find((item) => item.status === "active") ?? theses[0] ?? null;
  const nextReviewDate = watchlist.find((item) => item.active && item.next_review_date)?.next_review_date ?? null;
  const linkedEvidenceCount = new Set(theses.flatMap((item) => item.evidence_ids)).size;
  const latestReminder = reminders[0] ?? null;

  const refresh = async () => {
    if (staticMode) {
      setError(null);
      setResearchRevision((current) => current + 1);
      return;
    }
    const [nextTheses, nextWatchlist, nextReminders] = await Promise.allSettled([
      api.listTheses(),
      api.listWatchlist(),
      api.listResearchReminders(),
    ]);
    if (nextTheses.status === "fulfilled") setTheses(nextTheses.value);
    if (nextWatchlist.status === "fulfilled") setWatchlist(nextWatchlist.value);
    if (nextReminders.status === "fulfilled") setReminders(nextReminders.value);
    setResearchRevision((current) => current + 1);
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
      const nextThesis: InvestmentThesis = {
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
      };
      if (staticMode) setTheses((current) => [nextThesis, ...current]);
      else await api.saveThesis(nextThesis);
      setStatement("");
      setDisconfirming("");
      setDrivers("");
      setMetrics("");
      setComposerOpen(false);
      if (!staticMode) await refresh();
    } catch {
      setError("Thesis could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const addToWatchlist = async (thesis: InvestmentThesis) => {
    const existing = watchlist.find((item) => item.ticker === thesis.ticker);
    const timestamp = now();
    const nextItem: WatchlistItem = {
      ticker: thesis.ticker,
      thesis_ids: Array.from(new Set([...(existing?.thesis_ids ?? []), thesis.thesis_id])),
      monitoring_questions: existing?.monitoring_questions ?? [],
      next_review_date: reviewDates[thesis.thesis_id] || existing?.next_review_date || null,
      active: true,
      updated_at: timestamp,
    };
    if (staticMode) setWatchlist((current) => [nextItem, ...current.filter((item) => item.ticker !== thesis.ticker)]);
    else {
      await api.saveWatchlistItem(nextItem);
      await refresh();
    }
  };

  const review = async (
    thesis: InvestmentThesis,
    outcome: ThesisReview["outcome"],
  ) => {
    const notes = reviewNotes[thesis.thesis_id]?.trim();
    if (!notes) return;
    const nextReview: ThesisReview = {
      review_id: id("review"),
      reviewed_at: now(),
      outcome,
      notes,
      evidence_ids: [],
    };
    if (staticMode) {
      setTheses((current) => current.map((item) => item.thesis_id === thesis.thesis_id
        ? { ...item, reviews: [...item.reviews, nextReview], updated_at: now() }
        : item));
    } else await api.reviewThesis(thesis.thesis_id, nextReview);
    setReviewNotes((current) => ({ ...current, [thesis.thesis_id]: "" }));
    if (!staticMode) await refresh();
  };

  return (
    <div className="journal-workspace" data-testid="research-journal">
      <section className="journal-position-brief" aria-label="Research memory brief">
        <header><div><span className="page-eyebrow">Current research position</span><h2>Journal brief</h2></div><span>{theses.length} saved thesis{theses.length === 1 ? "" : "es"}</span></header>
        <div className="journal-position-grid">
          <div><span>Active thesis</span><strong>{activeThesis?.ticker ?? "None"}</strong><small>{activeThesis?.time_horizon ?? "Create a thesis to begin"}</small></div>
          <div><span>Next review</span><strong>{displayDate(nextReviewDate)}</strong><small>{nextReviewDate ? "Scheduled research checkpoint" : "No review date"}</small></div>
          <div><span>Open diligence</span><strong className={reminders.length ? "review-emphasis" : ""}>{reminders.length}</strong><small>{latestReminder ? "Research item awaiting review" : "Nothing awaiting review"}</small></div>
          <div><span>Evidence linked</span><strong>{linkedEvidenceCount}</strong><small>Source IDs across active theses</small></div>
        </div>
      </section>

      <div className="journal-layout">
        <aside className="journal-memory-rail">
          <section className="section thesis-focus-card">
            <header><div><span className="page-eyebrow">Thesis spine</span><h2>{activeThesis?.ticker ?? "No active thesis"}</h2></div>{activeThesis ? <span className={`thesis-state ${activeThesis.status}`}>{activeThesis.status}</span> : null}</header>
            {activeThesis ? <>
              <p className="thesis-focus-statement">{activeThesis.statement}</p>
              <div className="thesis-driver-list">{activeThesis.key_drivers.map((driver) => <span key={driver}>{driver}</span>)}</div>
              <div className="thesis-falsification"><Target size={17} aria-hidden="true" /><div><strong>What would disprove it</strong><ul>{activeThesis.disconfirming_conditions.map((condition) => <li key={condition}>{condition}</li>)}</ul></div></div>
              <footer><span>{activeThesis.evidence_ids.length} evidence IDs · {activeThesis.reviews.length} reviews</span><button className="text-action" type="button" onClick={() => setActiveTask("reviews")}>Open review</button></footer>
            </> : <p className="quiet-empty">Create a thesis with a falsification condition to start a durable research record.</p>}
          </section>

          <details className="journal-compose section" open={composerOpen} onToggle={(event) => setComposerOpen(event.currentTarget.open)}>
            <summary><span><Plus size={16} aria-hidden="true" />Create a thesis</span><ChevronDown size={16} aria-hidden="true" /></summary>
            <div className="journal-compose-fields">
              <label>Ticker<input name="thesis_ticker" autoComplete="off" spellCheck={false} value={ticker} onChange={(event) => setTicker(event.target.value)} /></label>
              <label>Thesis<textarea name="thesis_statement" autoComplete="off" value={statement} onChange={(event) => setStatement(event.target.value)} /></label>
              <label>Time horizon<input name="thesis_time_horizon" autoComplete="off" value={timeHorizon} onChange={(event) => setTimeHorizon(event.target.value)} /></label>
              <label>What would disprove it?<textarea name="thesis_disconfirming" autoComplete="off" value={disconfirming} onChange={(event) => setDisconfirming(event.target.value)} placeholder="Comma-separated falsification conditions…" /></label>
              <label>Key drivers<input name="thesis_drivers" autoComplete="off" value={drivers} onChange={(event) => setDrivers(event.target.value)} placeholder="pricing, product mix…" /></label>
              <label>Metrics to monitor<input name="thesis_metrics" autoComplete="off" spellCheck={false} value={metrics} onChange={(event) => setMetrics(event.target.value)} placeholder="gross_margin, revenue…" /></label>
              <button className="primary" type="button" disabled={busy || !ticker || !statement || !disconfirming} onClick={() => void saveThesis()}>Save active thesis</button>
              {error ? <div className="recoverable-error" role="alert"><p>{error}</p><button className="ghost" type="button" onClick={() => void refresh()}>Retry journal</button></div> : null}
            </div>
          </details>

          {reminders.length ? <section className="section reminder-ledger"><h2>Due research</h2>{reminders.map((reminder) => <article className={reminder.overdue ? "overdue" : ""} key={reminder.reminder_id}><CalendarClock size={16} aria-hidden="true" /><div><strong>{reminder.ticker}</strong><span>{reminder.title}</span><small>{reminder.overdue ? "Overdue" : "Due"} {reminder.due_date}</small></div></article>)}</section> : null}
          <section className="section watchlist-ledger"><h2>Watchlist</h2>{watchlist.length ? watchlist.map((item) => <article key={item.ticker}><strong>{item.ticker}</strong><span>{item.thesis_ids.length} linked thesis</span><small>{item.next_review_date ? `Review ${displayDate(item.next_review_date)}` : "Review date not set"}</small></article>) : <p className="muted">Link a thesis to start the watchlist.</p>}</section>
        </aside>

        <div className="journal-main">
          <nav className="research-task-nav" aria-label="Research tasks">
            {(["cycle", "valuation", "peers", "reviews"] as ResearchTask[]).map((task) => <button key={task} type="button" className={activeTask === task ? "active" : ""} aria-current={activeTask === task ? "page" : undefined} onClick={() => setActiveTask(task)}>{task === "cycle" ? "Research cycle" : task === "valuation" ? "Valuation" : task === "peers" ? "Peer analysis" : "Reviews"}</button>)}
          </nav>
          <ResearchCyclePanel activeTask={activeTask} researchRevision={researchRevision} staticMode={staticMode} />

          <details className="section thesis-ledger-section">
            <summary><span>Thesis archive</span><small>{theses.length} records</small><ChevronDown size={16} aria-hidden="true" /></summary>
            <div className="thesis-list">
              {theses.map((thesis) => <article className={`thesis-card ${thesis.status}`} key={thesis.thesis_id}><header><div><strong>{thesis.ticker}</strong><span>{thesis.status}</span></div><small>{thesis.time_horizon}</small></header><div className="thesis-meta"><span>Drivers: {thesis.key_drivers.join(", ") || "—"}</span><span>Monitor: {thesis.monitoring_metrics.join(", ") || "—"}</span><span>{thesis.reviews.length} reviews</span></div><div className="thesis-actions"><input type="date" aria-label={`Next review date for ${thesis.ticker}`} value={reviewDates[thesis.thesis_id] ?? ""} onChange={(event) => setReviewDates((current) => ({ ...current, [thesis.thesis_id]: event.target.value }))} /><button className="ghost" type="button" onClick={() => void addToWatchlist(thesis)}>Add to watchlist</button><input aria-label={`Review notes for ${thesis.ticker}`} value={reviewNotes[thesis.thesis_id] ?? ""} onChange={(event) => setReviewNotes((current) => ({ ...current, [thesis.thesis_id]: event.target.value }))} placeholder="Review evidence and outcome" /><button className="ghost" type="button" onClick={() => void review(thesis, "supported")}>Supported</button><button className="ghost" type="button" onClick={() => void review(thesis, "mixed")}>Mixed</button><button className="ghost danger" type="button" onClick={() => void review(thesis, "invalidated")}>Invalidated</button></div></article>)}
              {!theses.length ? <p className="muted">No saved thesis yet.</p> : null}
            </div>
          </details>
          <details className="section operations-boundary"><summary>Local data & scheduling</summary><p>Database migration, backup, restore, API keys, TLS, and system schedulers remain administrator operations. Run them through the documented CLI on the host; the browser does not expose destructive database controls.</p></details>
        </div>
      </div>
    </div>
  );
}
