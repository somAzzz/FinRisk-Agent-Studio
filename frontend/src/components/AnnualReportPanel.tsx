import { useEffect, useState } from "react";
import { api, clearApiCache, describeApiError, FinRiskApiError, type AnnualJob } from "../api";
import { reportRoute } from "../annual/model";

const memoryKey = "finrisk-annual-job";
export function AnnualReportPanel() {
  const [mode, setMode] = useState("file"),
    [file, setFile] = useState<File | null>(null),
    [url, setUrl] = useState(""),
    [goal, setGoal] = useState(""), [asOf,setAsOf]=useState("");
  const [job, setJob] = useState<AnnualJob | null>(() => {
    const id = sessionStorage.getItem(memoryKey);
    return id ? { id, status: "queued" } : null;
  });
  const [error, setError] = useState(""),
    [sending, setSending] = useState(false),
    [retry, setRetry] = useState(0);
  const active = job?.status === "running" || job?.status === "queued";
  useEffect(() => {
    if (!job?.id || !active) return;
    let live = true,
      timer: ReturnType<typeof setTimeout>;
    const id = job.id;
    async function check() {
      try {
        const next = await api.annualJob(id);
        if (!live) return;
        setError("");
        setJob(next);
        if (next.status === "completed")
          clearApiCache("/workflows/annual-report/library");
        if (next.status === "queued" || next.status === "running")
          timer = setTimeout(check, 3000);
      } catch (e) {
        if (live) {
          if (e instanceof FinRiskApiError && e.status === 404) {
            sessionStorage.removeItem(memoryKey);
            setJob(null);
          }
          setError(describeApiError(e, "Analysis status"));
        }
      }
    }
    void check();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [job?.id, active, retry]);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (sending || active) return;
    setSending(true);
    setError("");
    try {
      const settings={...(asOf?{as_of:asOf}:{}),...(goal.trim()?{goal:goal.trim()}:{})};
      const source = mode === "file" ? file : url.trim();
      if (!source) {
        setError("Select a report first.");
        return;
      }
      const next = await api.startAnnualJob(source, settings);
      sessionStorage.setItem(memoryKey, next.id);
      setJob(next);
    } catch (e) {
      setError(describeApiError(e,"Annual report"));
    } finally {
      setSending(false);
    }
  }
  return (
    <section aria-label="Annual report analysis" className="filing-intake">
      <form onSubmit={submit}>
        <label>
          Report source{" "}
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="file">Local file</option>
            <option value="url">Public URL</option>
          </select>
        </label>
        {mode === "file" ? (
          <input
            aria-label="Report file"
            required
            type="file"
            accept=".pdf,.xhtml,.html,.zip"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        ) : (
          <input
            aria-label="Report URL"
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        )}
        <label>Research question (optional)<textarea value={goal} maxLength={2000} onChange={e=>setGoal(e.target.value)} placeholder="Which changes in the business need follow-up?" /></label>
        <label>Evidence cutoff (optional)<input type="date" value={asOf} onChange={e=>setAsOf(e.target.value)}/></label>
        <small>Leave the date blank to use the current research date.</small>
        <button type="submit" disabled={sending || active}>
          {sending
            ? "Submitting…"
            : active
              ? "Analysis in progress…"
              : "Analyze report"}
        </button>
      </form>
      {active && (
        <p role="status">
          {job.status === "queued" ? "Queued" : "Analyzing the document"} · You
          can close this panel and return to it for progress.
        </p>
      )}
      {error && (
        <p role="alert">
          {error}{" "}
          {active && (
            <button onClick={() => setRetry((n) => n + 1)}>Retry status</button>
          )}
        </p>
      )}
      {job?.status === "failed" && (
        <p role="alert">{job.detail || "Analysis failed."}</p>
      )}
      {job?.status === "completed" && job.report_id && (
        <p role="status">
          Analysis saved.{" "}
          <a href={reportRoute(job.report_id)}>Open saved annual report →</a>
        </p>
      )}
    </section>
  );
}
