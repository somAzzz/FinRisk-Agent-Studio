import { ArrowRight, FileSearch, Play, ShieldAlert } from "lucide-react";
import { kindLabel, type RunHistoryItem } from "./RunHistoryPanel";

interface Props {
  historyItems: RunHistoryItem[];
  staticMode: boolean;
  incomplete?: boolean;
  onSelect: (item: RunHistoryItem) => void;
  onOpenRuns: () => void;
  onStartResearch: () => void;
}

export function TodayDashboard({
  historyItems,
  staticMode,
  onSelect,
  incomplete = false,
  onOpenRuns,
  onStartResearch,
}: Props) {
  const reviewRows = historyItems.filter((x) => x.status === "needs_review");
  return (
    <main className="today-page product-page" id="main-content" tabIndex={-1}>
      <header className="page-heading today-heading">
        <div>
          <span className="page-eyebrow">
            {staticMode ? "Archived demonstration" : "Research desk"}
          </span>
          <h1>Research queue</h1>
          <p>
            Start with the evidence changes that can alter your current view.
          </p>
        </div>
        <button
          className="product-primary"
          type="button"
          onClick={onStartResearch}
        >
          <Play size={16} aria-hidden="true" />
          Start research
        </button>
      </header>

      {incomplete && (
        <p role="status">
          Some research sources could not be loaded. Counts cover the available
          records only.
        </p>
      )}
      <section className="queue-summary" aria-label="Research queue summary">
        <div>
          <ShieldAlert size={19} aria-hidden="true" />
          <span>Needs review</span>
          <strong>{reviewRows.length}</strong>
        </div>
        <div>
          <FileSearch size={19} aria-hidden="true" />
          <span>Saved items</span>
          <strong>{historyItems.length}</strong>
        </div>
      </section>

      <div className="today-grid">
        <section className="queue-panel">
          <header className="section-heading-row">
            <div>
              <span className="page-eyebrow">Analyst decisions</span>
              <h2>Needs review</h2>
            </div>
            <span className="count-chip">{reviewRows.length}</span>
          </header>
          {reviewRows.length ? (
            <div className="queue-list">
              {reviewRows.map((row) => (
                <article className="queue-row" key={row.kind + row.runId}>
                  <div className="company-monogram" aria-hidden="true">
                    {kindLabel(row.kind)[0]}
                  </div>
                  <div className="queue-company">
                    <strong>{kindLabel(row.kind)}</strong>
                    <span>{row.title}</span>
                  </div>
                  <p>{row.detail}</p>
                  <button
                    className="product-secondary"
                    type="button"
                    onClick={() => onSelect(row)}
                  >
                    Review <ArrowRight size={14} aria-hidden="true" />
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <div className="directed-empty">
              <ShieldAlert size={24} aria-hidden="true" />
              <div>
                <strong>
                  {incomplete
                    ? "No review items in the available records."
                    : "No items marked for review."}
                </strong>
                <p>
                  Saved reports and investigations appear here when they need a
                  decision.
                </p>
              </div>
              <button
                className="product-secondary"
                type="button"
                onClick={onStartResearch}
              >
                Start research
              </button>
            </div>
          )}
        </section>

        <aside
          className="activity-column"
          aria-label="Recent research activity"
        >
          <header className="section-heading-row">
            <div>
              <span className="page-eyebrow">Audit trail</span>
              <h2>Research activity</h2>
            </div>
            <button className="text-action" type="button" onClick={onOpenRuns}>
              View all
            </button>
          </header>
          {historyItems.length ? (
            <ol className="activity-list">
              {historyItems.slice(0, 5).map((item) => (
                <li key={`${item.kind}:${item.runId}`}>
                  <span
                    className={`activity-dot ${item.status}`}
                    aria-hidden="true"
                  />
                  <div>
                    <button
                      type="button"
                      className="text-action"
                      onClick={() => onSelect(item)}
                    >
                      {item.title}
                    </button>
                    <span>{item.detail ?? item.runId}</span>
                  </div>
                  <small>{kindLabel(item.kind)}</small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="quiet-empty">
              Runs will appear here with their quality and review state.
            </p>
          )}
        </aside>
      </div>
    </main>
  );
}
