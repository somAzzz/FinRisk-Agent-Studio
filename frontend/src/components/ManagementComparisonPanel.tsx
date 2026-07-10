import { useState } from "react";
import { api } from "../api";
import type { ManagementComparisonResponse } from "../types";

interface Props { ticker: string | null; }

export function ManagementComparisonPanel({ ticker }: Props) {
  const [year, setYear] = useState("");
  const [quarter, setQuarter] = useState("");
  const [compareYear, setCompareYear] = useState("");
  const [compareQuarter, setCompareQuarter] = useState("");
  const [result, setResult] = useState<ManagementComparisonResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!ticker) return null;

  const load = async () => {
    const rawValues = [year, quarter, compareYear, compareQuarter];
    const values = rawValues.map(Number);
    if (
      rawValues.some((value) => !value.trim())
      || values.some((value) => !Number.isInteger(value))
      || values[0] < 1990
      || values[2] < 1990
      || values[1] < 1 || values[1] > 4
      || values[3] < 1 || values[3] > 4
    ) {
      setError("Select both transcript periods before comparing.");
      return;
    }
    setLoading(true);
    try {
      setResult(await api.getManagementComparison(
        ticker, values[0], values[1], values[2], values[3],
      ));
      setError(null);
    } catch {
      setError("Transcript comparison is unavailable for the selected periods.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <details className="section management-panel" data-testid="management-panel">
      <summary><span>Management signal comparison</span><small>Prepared remarks vs Q&amp;A</small></summary>
      <div className="management-periods">
        <fieldset><legend>Current call</legend><label>Year<input aria-label="Current transcript year" value={year} onChange={(event) => setYear(event.target.value)} /></label><label>Quarter<select aria-label="Current transcript quarter" value={quarter} onChange={(event) => setQuarter(event.target.value)}><option value="">—</option>{[1,2,3,4].map((value) => <option key={value} value={value}>Q{value}</option>)}</select></label></fieldset>
        <fieldset><legend>Compare with</legend><label>Year<input aria-label="Comparison transcript year" value={compareYear} onChange={(event) => setCompareYear(event.target.value)} /></label><label>Quarter<select aria-label="Comparison transcript quarter" value={compareQuarter} onChange={(event) => setCompareQuarter(event.target.value)}><option value="">—</option>{[1,2,3,4].map((value) => <option key={value} value={value}>Q{value}</option>)}</select></label></fieldset>
        <button className="primary" type="button" disabled={loading} onClick={() => void load()}>{loading ? "Comparing…" : "Compare calls"}</button>
      </div>
      {error ? <p className="journal-error">{error}</p> : null}
      {result ? (
        <div className="management-results">
          <div className="management-kpis"><div><span>Overall tone</span><strong>{result.current.overall_tone}</strong></div><div><span>Prepared</span><strong>{result.current.prepared_remarks_tone}</strong></div><div><span>Q&amp;A</span><strong>{result.current.qa_tone}</strong></div><div><span>Guidance</span><strong>{result.current.guidance_signal}</strong></div><div><span>Uncertainty</span><strong>{Math.round(result.current.uncertainty * 100)}%</strong></div></div>
          <h3>Changes vs {result.previous ? `${result.previous.year}Q${result.previous.quarter}` : "prior call"}</h3>
          {result.changes.length ? <div className="management-change-list">{result.changes.map((change) => <article key={change.dimension}><span>{change.dimension}</span><strong>{String(change.previous_value)} → {String(change.current_value)}</strong><b className={change.direction}>{change.direction}</b><small>{change.evidence_ids.join(", ")}</small></article>)}</div> : <p className="muted">No material rule-based signal change detected.</p>}
          <h3>Current topic signals</h3>
          <div className="topic-signal-list">{result.current.topic_signals.map((topic) => <span key={topic.topic}>{topic.topic}: <b>{topic.sentiment}</b></span>)}</div>
        </div>
      ) : null}
    </details>
  );
}
