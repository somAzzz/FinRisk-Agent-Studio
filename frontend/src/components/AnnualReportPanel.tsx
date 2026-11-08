import { useState } from "react";
import { api, describeApiError, type AnnualReportResult } from "../api";

export function AnnualReportPanel() {
  const [mode, setMode] = useState<"file" | "url">("file");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<AnnualReportResult | null>(null);
  const [options, setOptions] = useState("{}");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError("");
    setReport(null);
    setBusy(true);
    try {
      const settings = JSON.parse(options);
      const source = mode === "file" ? file : url.trim();
      if (!source) throw new Error("Select a report first.");
      setReport(await api.analyzeAnnualReport(source, settings));
    } catch (err) {
      setError(err instanceof SyntaxError ? "Analysis options must be valid JSON." : describeApiError(err, "Annual report"));
    } finally {
      setBusy(false);
    }
  }
  return <details className="runtime-disclosure">
    <summary>Analyze an annual report</summary>
    <form onSubmit={submit}>
      <label>Report source <select value={mode} onChange={e => setMode(e.target.value as typeof mode)}>
        <option value="file">Local file</option><option value="url">Public URL</option>
      </select></label>
      {mode === "file" ? <input aria-label="Report file" type="file" required accept=".pdf,.xhtml,.html,.zip"
        onChange={e => setFile(e.target.files?.[0] ?? null)} /> :
        <input aria-label="Report URL" type="url" required value={url} onChange={e => setUrl(e.target.value)} />}
      <details><summary>Analysis options</summary>
        <label>JSON options for the analysis date, external sources and scenarios
          <textarea value={options} onChange={e => setOptions(e.target.value)} />
        </label>
      </details>
      <button type="submit" disabled={busy}>{busy ? "Analyzing report…" : "Analyze report"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {report && <section aria-label="Annual report analysis">
      <h3>{report.identity.cover.join(" ") || "Annual report"}</h3>
      <p>{report.status} · {report.sources.annual.page_count} document pages</p>
      {report.findings.map((finding, index) => <article key={index}>
        <h4>{finding.subject} · {finding.status}</h4><small>Model interpretation · review against cited passages</small><p>{finding.assessment}</p>
        {finding.evidence.map((c, i) => <blockquote key={i}>{c.quote} ({c.source_id}, p. {c.physical_page})</blockquote>)}
        <dl><dt>What could change this judgment?</dt><dd>{finding.contrary_evidence_or_test}</dd>
          <dt>Missing data</dt><dd>{finding.missing_data}</dd><dt>Decision to evaluate</dt><dd>{finding.decision}</dd></dl>
      </article>)}
      {!!report.chart_rows?.length && <table>
        <caption>Chart values and published changes</caption>
        <thead><tr>{["Source", "Metric", "Prior year", "Current year", "Change"].map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{report.chart_rows.map((row, i) => <tr key={i}>
          <td>{row.chart_id} · PDF p. {row.physical_page}</td><th scope="row">{row.metric}</th>
          {[row.change.from_year, row.change.to_year].map(year => <td key={year}>{year} · {row.values[year]} {row.unit}</td>)}
          <td>{row.change.value} {row.change.unit}</td>
        </tr>)}</tbody>
      </table>}
      {report.reconciliations.map((r,i) => <p key={i}>{r.metric} · {r.calculated.join(" / ")} {r.unit} · {r.status} (PDF p. {r.physical_page})</p>)}
      {report.warnings.map((w,i) => <p key={i}>{w}</p>)}
      <details><summary>Full evidence and calculations</summary><pre>{JSON.stringify(report, null, 2)}</pre></details>
    </section>}
  </details>;
}
