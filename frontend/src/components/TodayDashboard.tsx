import {
  ArrowRight,
  CalendarDays,
  FileSearch,
  Play,
  ShieldAlert,
} from "lucide-react";
import type { RunHistoryItem } from "./RunHistoryPanel";

interface Props {
  historyItems: RunHistoryItem[];
  hasCompanyBrief: boolean;
  onOpenCompany: () => void;
  onOpenRuns: () => void;
  onStartResearch: () => void;
}

function timeLabel(index: number): string {
  if (index === 0) return "Latest";
  if (index === 1) return "Earlier today";
  return "Recent";
}

export function TodayDashboard({
  historyItems,
  hasCompanyBrief,
  onOpenCompany,
  onOpenRuns,
  onStartResearch,
}: Props) {
  const reviewRows = hasCompanyBrief
    ? [
        {
          ticker: "AAPL",
          title: "Apple Inc.",
          reason: "Supply-chain concentration changed and needs analyst review.",
          materiality: "High",
          evidence: 1,
        },
      ]
    : [];

  return (
    <main className="today-page product-page" id="main-content" tabIndex={-1}>
      <header className="page-heading today-heading">
        <div>
          <span className="page-eyebrow">Sunday, July 12, 2026</span>
          <h1>Research queue</h1>
          <p>Start with the evidence changes that can alter your current view.</p>
        </div>
        <button className="product-primary" type="button" onClick={onStartResearch}>
          <Play size={16} aria-hidden="true" />
          Start research
        </button>
      </header>

      <section className="queue-summary" aria-label="Research queue summary">
        <div>
          <ShieldAlert size={19} aria-hidden="true" />
          <span>Needs review</span>
          <strong>{reviewRows.length}</strong>
        </div>
        <div>
          <FileSearch size={19} aria-hidden="true" />
          <span>Recent runs</span>
          <strong>{historyItems.length}</strong>
        </div>
        <div>
          <CalendarDays size={19} aria-hidden="true" />
          <span>Next scheduled check</span>
          <strong>Jul 13</strong>
        </div>
      </section>

      <div className="today-grid">
        <section className="queue-panel">
          <header className="section-heading-row">
            <div>
              <span className="page-eyebrow">Priority first</span>
              <h2>Needs review</h2>
            </div>
            <span className="count-chip">{reviewRows.length}</span>
          </header>
          {reviewRows.length ? (
            <div className="queue-list">
              {reviewRows.map((row) => (
                <article className="queue-row" key={row.ticker}>
                  <div className="company-monogram" aria-hidden="true">{row.ticker.slice(0, 1)}</div>
                  <div className="queue-company">
                    <strong>{row.ticker}</strong>
                    <span>{row.title}</span>
                  </div>
                  <p>{row.reason}</p>
                  <div className="queue-meta">
                    <span className="materiality high">{row.materiality}</span>
                    <span>{row.evidence} evidence item</span>
                  </div>
                  <button className="product-secondary" type="button" onClick={onOpenCompany}>
                    Review <ArrowRight size={14} aria-hidden="true" />
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <div className="directed-empty">
              <ShieldAlert size={24} aria-hidden="true" />
              <div>
                <strong>No evidence changes need review yet.</strong>
                <p>Run a company update to establish the first monitored baseline.</p>
              </div>
              <button className="product-secondary" type="button" onClick={onStartResearch}>
                Run first update
              </button>
            </div>
          )}
        </section>

        <aside className="activity-column" aria-label="Recent research activity">
          <header className="section-heading-row">
            <div>
              <span className="page-eyebrow">Audit trail</span>
              <h2>Recent activity</h2>
            </div>
            <button className="text-action" type="button" onClick={onOpenRuns}>View all</button>
          </header>
          {historyItems.length ? (
            <ol className="activity-list">
              {historyItems.slice(0, 5).map((item, index) => (
                <li key={`${item.kind}:${item.runId}`}>
                  <span className={`activity-dot ${item.status}`} aria-hidden="true" />
                  <div>
                    <strong>{item.title}</strong>
                    <span>{item.detail ?? item.runId}</span>
                  </div>
                  <small>{timeLabel(index)}</small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="quiet-empty">Runs will appear here with their quality and review state.</p>
          )}
        </aside>
      </div>
    </main>
  );
}
