import { useEffect, useState } from "react";
import { api, describeApiError } from "../api";
import {
  type CompanyDesk as Desk,
  type CompanyScope,
  type Filing,
  issuerRoute,
} from "./company";
import { label, reportRoute, indexRoute, sample } from "./model";
import "./annual.css";

function PageRef({ filing, page }: { filing: Filing; page: number }) {
  const url = filing.original;
  return url && (/^https?:\/\//.test(url) || url.startsWith("/workflows/")) ? (
    <a href={url + "#page=" + page} target="_blank" rel="noreferrer">
      PDF p. {page} ↗
    </a>
  ) : (
    <>p. {page}</>
  );
}
export default function CompanyDesk({
  id,
  day,
  staticMode,
  start,
  journal,
  brief,
}: {
  id: string;
  day: string;
  staticMode: boolean;
  start: (s: CompanyScope) => void;
  journal: (s: CompanyScope) => void;
  brief: (id: string) => void;
}) {
  const [desk, setDesk] = useState<Desk | null>(null),
    [error, setError] = useState(""),
    [metric, setMetric] = useState("Operatives Ergebnis");
  useEffect(() => {
    let active = true;
    setError("");
    setDesk(null);
    const req = staticMode
      ? sample<Desk>(
          "issuer/" +
            encodeURIComponent(id) +
            "/" +
            (day || "latest") +
            ".json",
        )
      : api.companyWorkspace(id, day);
    req
      .then((x) => {
        if (active) {
          setDesk(x);
          try {
            sessionStorage.setItem(
              "finrisk:last-company",
              issuerRoute(x.id, day || undefined),
            );
          } catch {
            /* Storage is optional. */
          }
        }
      })
      .catch((e) => {
        if (active) setError(describeApiError(e, "Company workspace"));
      });
    return () => {
      active = false;
    };
  }, [id, day, staticMode]);
  if (!desk)
    return (
      <div className="ar">
        <a href={indexRoute}>← Annual report library</a>
        <p role={error ? "alert" : "status"}>
          {error || "Opening company research…"}
        </p>
        {error && <a href={issuerRoute(id)}>Open latest workspace</a>}
      </div>
    );
  const filings = Object.fromEntries(desk.filings.map((f) => [f.id, f])),
    latest = desk.filings[desk.filings.length - 1],
    symbol = latest.issuer.listings?.[0]?.symbol;
  const scope = symbol ? { id, ticker: symbol, name: desk.name } : null;
  return (
    <div className="ar company-dossier">
      <a className="ar-back" href={indexRoute}>
        ← Annual report library
      </a>
      <header className="ar-mast">
        <div>
          <span className="ar-kicker">
            Company workspace · Verified legal entity
          </span>
          <h1>{desk.name}</h1>
          <p>
            {desk.id} · {symbol || "Listing unknown"} · Evidence through{" "}
            {desk.as_of}
          </p>
        </div>
        {!staticMode && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              window.location.hash = issuerRoute(
                id,
                String(new FormData(e.currentTarget).get("day")),
              );
            }}
          >
            <label>
              Evidence through
              <input
                required
                type="date"
                name="day"
                defaultValue={desk.as_of}
              />
            </label>
            <button>Replay</button>
          </form>
        )}
      </header>
      <section>
        <h2>Filings and identity</h2>
        <p>
          Each filing is linked by the issuer’s own registration disclosure.
        </p>
        {desk.filings.map((f) => (
          <article key={f.id} className="ar-item">
            <a
              href={
                reportRoute(f.id) +
                "?" +
                new URLSearchParams({ day: f.cutoff, companyDay: desk.as_of })
              }
            >
              {f.period} · Open filing →
            </a>{" "}
            · Published{" "}
            <a
              href={issuerRoute(id, f.published)}
              title="Replay the company workspace on publication"
            >
              {f.published}
            </a>
            <details>
              <summary>Identity evidence</summary>
              <p>
                {f.issuer.registration?.quote}{" "}
                {f.issuer.registration && (
                  <PageRef filing={f} page={f.issuer.registration.page} />
                )}
              </p>
              {f.issuer.listings?.map((x) => (
                <p key={x.isin}>
                  {x.symbol} · {x.qualified} · ISIN {x.isin} ·{" "}
                  <PageRef filing={f} page={x.page} />
                </p>
              ))}
              <small>Document SHA-256: {f.sha256}</small>
            </details>
          </article>
        ))}
      </section>
      <section>
        <h2>Segment changes across filings</h2>
        <p>
          Each annual value comes from its own filing. The newer filing’s
          comparative must also agree before a change is shown.
        </p>
        {!desk.comparisons.length && (
          <p>
            Only one eligible fiscal year. A comparison is not yet available.
          </p>
        )}
        {desk.comparisons.map((c) => {
          const metrics = [...new Set(c.rows.map((r) => r.metric))],
            chosen = metrics.includes(metric) ? metric : metrics[0];
          return (
            <div key={c.from + c.to}>
              <h3>
                {filings[c.from].period} → {filings[c.to].period}
              </h3>
              {metrics.length ? (
                <>
                  <label>
                    Measure{" "}
                    <select
                      value={chosen}
                      onChange={(e) => setMetric(e.target.value)}
                    >
                      {metrics.map((m) => (
                        <option value={m} key={m}>
                          {label(m)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Segment</th>
                          <th>Prior</th>
                          <th>Current</th>
                          <th>Change</th>
                          <th>Unit</th>
                          <th>Sources</th>
                        </tr>
                      </thead>
                      <tbody>
                        {c.rows
                          .filter((r) => r.metric === chosen)
                          .map((r) => (
                            <tr key={r.segment}>
                              <th>{label(r.segment)}</th>
                              <td>{r.prior ?? "unknown"}</td>
                              <td>{r.current ?? "unknown"}</td>
                              <td>{r.change ?? "unknown"}</td>
                              <td>{r.unit}</td>
                              <td>
                                <details>
                                  <summary>Verify</summary>
                                  <p>
                                    {r.quotes[0]} ·{" "}
                                    <PageRef
                                      filing={filings[c.from]}
                                      page={r.pages[0]}
                                    />
                                  </p>
                                  <p>
                                    {r.quotes[1]} ·{" "}
                                    <PageRef
                                      filing={filings[c.to]}
                                      page={r.pages[1]}
                                    />
                                  </p>
                                  {r.status !== "comparable" && (
                                    <p>Comparable basis not verified.</p>
                                  )}
                                </details>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <p>No verified comparable basis.</p>
              )}
            </div>
          );
        })}
      </section>
      <section>
        <h2>Question history</h2>
        {!desk.questions.length && <p>No saved questions for these filings.</p>}
        {desk.questions.map((q) => (
          <article key={q.origin + q.id} className="ar-item">
            <small>
              {filings[q.origin].period} ·{" "}
              {q.kind === "disclosed_outlook"
                ? "Disclosed outlook"
                : "Original tracking question"}
            </small>
            <h3>{q.question}</h3>
            <p>
              Answer: <strong>{q.status.replace(/_/g, " ")}</strong> ·
              Fulfilment: {q.fulfillment}
            </p>
            {q.quote && (
              <p>
                {q.quote} ·{" "}
                <PageRef filing={filings[q.origin]} page={q.page!} />
              </p>
            )}
            {q.answer && (
              <p>
                Reported:{" "}
                <b>
                  {q.answer.value} {q.unit}
                </b>{" "}
                · {q.answer.published} · {q.answer.quote} ·{" "}
                <PageRef
                  filing={filings[q.answer.report]}
                  page={q.answer.page}
                />
              </p>
            )}
            {q.required && (
              <>
                <p>Direct evidence needed: {q.required}</p>
                <a
                  href={
                    reportRoute(q.origin) +
                    "?" +
                    new URLSearchParams({
                      view: "tracking",
                      lane: "fresh",
                      day: q.cutoff!,
                      task: q.id,
                      companyDay: desk.as_of,
                    })
                  }
                >
                  Open original tracking question →
                </a>
              </>
            )}
            {Boolean(q.trail?.length) && (
              <details>
                <summary>Subsequent evidence trail ({q.trail!.length})</summary>
                <p>
                  Checked passages were retrieved for review. A checked or
                  rejected citation does not establish the answer.
                </p>
                {q.trail!.map((x) => (
                  <details key={x.digest + x.page + x.verdict}>
                    <summary>
                      Subsequent citation · {x.published} ·{" "}
                      {x.verdict.replace(/_/g, " ")}
                    </summary>
                    <p>{x.quote}</p>
                    <p>
                      {x.url ? (
                        <a
                          href={x.url + "#page=" + x.page}
                          target="_blank"
                          rel="noreferrer"
                        >
                          PDF p. {x.page} ↗
                        </a>
                      ) : (
                        <>Page {x.page}</>
                      )}{" "}
                      · Reviewed {x.reviewed} · SHA-256 {x.digest}
                    </p>
                  </details>
                ))}
              </details>
            )}
          </article>
        ))}
      </section>
      <div className="ar-grid">
        <section>
          <h2>Research briefs</h2>
          {desk.briefs.map((b) => (
            <article key={b.id}>
              <button onClick={() => brief(b.id)}>{b.title} →</button>
              <p>{b.summary}</p>
              <small>
                {b.ticker} · {b.date}
              </small>
            </article>
          ))}
          {!desk.briefs.length && (
            <p>No verified company brief at this cutoff.</p>
          )}
          {!staticMode && scope && (
            <button onClick={() => start(scope)}>Start a company brief</button>
          )}
        </section>
        <section>
          <h2>Research journal</h2>
          {desk.journal.map((t) => (
            <article key={t.id}>
              <h3>{t.title}</h3>
              <p>
                {t.ticker} · {t.date} · {t.status}
              </p>
              <small>Falsification: {t.conditions.join("; ")}</small>
            </article>
          ))}
          {!desk.journal.length && (
            <p>No verified journal entry at this cutoff.</p>
          )}
          {!staticMode && scope && (
            <button onClick={() => journal(scope)}>
              Write a company thesis
            </button>
          )}
        </section>
      </div>
    </div>
  );
}
