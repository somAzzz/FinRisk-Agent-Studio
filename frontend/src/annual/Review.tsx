import { lazy, Suspense } from "react";
import { caseProof, cited, Empty, ProofButton, useDesk } from "./context";
import {
  delta,
  endpoint,
  num,
  pretty,
  publicUrl,
  type Audit,
  type Scenario,
} from "./model";
export function Revisions({ audit, id }: { audit: Audit; id: string }) {
  const { b } = useDesk();
  return (
    <ol className="ar-revisions">
      {audit.history.map((h, i) => (
        <li key={i}>
          <strong>
            Revision {i + 1} · {pretty(h.verdict.status)}
          </strong>
          <p>{h.proposal.text}</p>
          <p>{h.verdict.reason}</p>
          <ProofButton
            id={id + "-" + i}
            proof={{
              title:
                h.verdict.status === "supported"
                  ? "Supporting passage"
                  : "Citation under review",
              detail:
                h.verdict.status === "supported"
                  ? undefined
                  : "This is the text submitted for review. It did not establish full support for the claim. " +
                    h.verdict.reason,
              origin: "Fact review · " + pretty(h.verdict.status),
              date: h.locator?.published,
              page: h.locator?.page,
              quote: h.verdict.quote,
              url:
                h.locator?.sha256 === b.meta.sha256
                  ? b.original
                  : publicUrl(h.locator?.source),
            }}
          >
            Inspect cited passage ↗
          </ProofButton>
        </li>
      ))}
      {audit.follow_up && (
        <li>
          <strong>Follow-up</strong>
          <p>{audit.follow_up.missing || audit.follow_up.question}</p>
        </li>
      )}
    </ol>
  );
}
function Values({ value }: { value: unknown }) {
  if (value == null) return <span>Unknown</span>;
  if (Array.isArray(value))
    return value.length ? (
      <ol>
        {value.map((v, i) => (
          <li key={i}>
            <Values value={v} />
          </li>
        ))}
      </ol>
    ) : (
      <span>No entries</span>
    );
  if (typeof value === "object")
    return (
      <dl className="ar-fields">
        {Object.entries(value).map(([k, v]) => (
          <div key={k}>
            <dt>{pretty(k)}</dt>
            <dd>
              <Values value={v} />
            </dd>
          </div>
        ))}
      </dl>
    );
  return typeof value === "string" && publicUrl(value) ? (
    <a href={value} target="_blank" rel="noreferrer">
      Open source ↗
    </a>
  ) : (
    <span>{String(value)}</span>
  );
}
export function Evidence() {
  const { b, p, go } = useDesk(),
    a = b.annual;
  const states = [...new Set(a.fact_reviews.map((v) => v.status))];
  return (
    <>
      <section>
        <span className="ar-kicker">Primary evidence</span>
        <h2>Findings & review</h2>
        <p>
          Read the supported observation before inspecting its review history.
        </p>
        {b.annual_review_available === false && (
          <Empty>
            The annual claim-review run is not available at this cutoff.
          </Empty>
        )}
        {!a.findings.length && b.annual_review_available !== false && (
          <Empty>No supported narrative findings in this run.</Empty>
        )}
        {a.findings.map((f, i) => (
          <article className="ar-item" key={i}>
            <small>{pretty(f.topic)}</small>
            <h3>{f.subject}</h3>
            <p>{f.assessment}</p>
            {f.evidence.map((c, j) => (
              <ProofButton
                key={j}
                id={"finding" + i + "-" + j}
                proof={cited(b, f.subject, c)}
              >
                Source · PDF p. {c.physical_page} ↗
              </ProofButton>
            ))}
            <details>
              <summary>Tests and decisions</summary>
              <dl>
                {[
                  [
                    "What could change the judgment?",
                    f.contrary_evidence_or_test,
                  ],
                  ["Missing evidence", f.missing_data],
                  ["Decision to evaluate", f.decision],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{v}</dd>
                  </div>
                ))}
              </dl>
            </details>
          </article>
        ))}
      </section>
      <section>
        <h3>Claim review queue</h3>
        <div className="ar-chips">
          {["all", ...states].map((s) => (
            <button
              key={s}
              aria-pressed={(p.status || "all") === s}
              onClick={() => go({ status: s, claim: "" })}
            >
              {pretty(s)} ·{" "}
              {
                a.fact_reviews.filter((v) => s === "all" || v.status === s)
                  .length
              }
            </button>
          ))}
        </div>
        {a.fact_reviews.map(
          (v, i) =>
            (!p.status || p.status === "all" || p.status === v.status) && (
              <article key={i} className="ar-item">
                <button
                  className="ar-disclose"
                  aria-expanded={p.claim === String(i)}
                  onClick={() =>
                    go({ claim: p.claim === String(i) ? "" : String(i) })
                  }
                >
                  {pretty(v.status)} · {v.history[0]?.proposal.text}
                </button>
                {p.claim === String(i) && (
                  <Revisions audit={v} id={"review" + i} />
                )}
              </article>
            ),
        )}
      </section>
      <section>
        <h3>Coverage and outstanding evidence</h3>
        {[
          ...a.warnings,
          ...a.unknown_topics.map((v) => "Uncovered topic: " + pretty(v)),
          ...a.decision_data_gaps,
        ].map((v, i) => (
          <p key={i}>{v}</p>
        ))}
        {Object.entries(a.sources).map(([k, s]) => (
          <p key={k}>
            {k} · {s.page_count} pages · {s.selected_pages?.length || 0}{" "}
            selected for interpretation ·{" "}
            {s.ocr_pages?.length
              ? "OCR: PDF p. " + s.ocr_pages.join(", ")
              : "No OCR pages"}
          </p>
        ))}
      </section>
      {(
        [
          "external_events",
          "market_observations",
          "scenarios",
          "plant_decisions",
          "inline_xbrl_facts",
        ] as const
      )
        .filter((k) => a[k]?.length)
        .map((k) => (
          <details key={k}>
            <summary>
              {pretty(k)} · {a[k].length} records
            </summary>
            <Values value={a[k]} />
          </details>
        ))}
    </>
  );
}
function Sensitivity({ s }: { s: Scenario }) {
  return (
    <details>
      <summary>Illustrative scenario · assumptions and calculation</summary>
      <p>Assumed inputs, not observed sales or an attributed loss.</p>
      <dl className="ar-fields">
        {Object.entries({
          ...s.assumptions,
          ...Object.fromEntries(
            Object.entries(s).filter(([k]) => k !== "assumptions"),
          ),
        }).map(([k, v]) => (
          <div key={k}>
            <dt>{pretty(k)}</dt>
            <dd>{String(v)}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
const Investigation = lazy(() =>
  import("../components/LLMAgentRunPanel").then((m) => ({
    default: m.LLMAgentRunPanel,
  })),
);
export function Tracking({
  canInvestigate = false,
}: {
  canInvestigate?: boolean;
}) {
  const { b, p, go } = useDesk(),
    r = b.reviewed,
    f = b.fresh,
    reviewed = p.lane === "reviewed";
  const searches = f?.search_trace?.filter((row) => "query" in row) ?? [];
  const decisions = f?.search_trace?.filter((row) => "decision" in row) ?? [];
  return (
    <>
      <section>
        <span className="ar-kicker">As of {b.cutoff}</span>
        <h2>Tracking & replay</h2>
        <div className="ar-chips">
          {[
            ["fresh", "Fresh automated tracking"],
            ["reviewed", "Reviewed case replay"],
          ].map(([k, v]) => (
            <button
              aria-pressed={reviewed === (k === "reviewed")}
              key={k}
              onClick={() => go({ lane: k, task: "", target: "" })}
            >
              {v}
            </button>
          ))}
        </div>
        {!reviewed ? (
          !f ? (
            <Empty>No fresh tracking snapshot for this run and date.</Empty>
          ) : (
            <>
              <h3>{f.alerts.length} new alerts</h3>
              <p>
                {f.tasks.length} research questions ·{" "}
                {f.eligible_digests.length} eligible originals. An absence of
                alerts does not establish normal supply.
              </p>
              {f.tasks.map((t, i) => (
                <article className="ar-item" key={t.id}>
                  <small>
                    {t.topic} · {pretty(t.action)}
                  </small>
                  <h4>{t.question}</h4>
                  <p>
                    Exposure: {t.state} · Fulfilment: {t.fulfillment}
                  </p>
                  <button
                    aria-expanded={p.task === t.id}
                    onClick={() => go({ task: p.task === t.id ? "" : t.id })}
                  >
                    Inspect task and search
                  </button>
                  {p.task === t.id && (
                    <>
                      <dl>
                        <dt>Search query</dt>
                        <dd>{t.query}</dd>
                        <dt>Evidence needed</dt>
                        <dd>{t.direct_evidence_needed}</dd>
                      </dl>
                      {canInvestigate && (
                        <div className="ar-followup">
                          {p.investigate === t.id ? (
                            <>
                              <h4>New investigation · {b.meta.company}</h4>
                              <p>
                                Starting point: {b.meta.period}, evidence as of{" "}
                                {b.cutoff}. New results belong to Research Runs
                                and do not change this historical snapshot.
                              </p>
                              <Suspense
                                fallback={<p>Loading investigation…</p>}
                              >
                                <Investigation
                                  key={b.meta.id + b.cutoff + t.id}
                                  initialRequest={{
                                    goal: t.question,
                                    workflow_kind: "company_research",
                                    filing_origin: {
                                      report_id: b.meta.id,
                                      cutoff: b.cutoff,
                                      task_id: t.id,
                                    },
                                  }}
                                />
                              </Suspense>
                            </>
                          ) : (
                            <button onClick={() => go({ investigate: t.id })}>
                              Investigate this question →
                            </button>
                          )}
                        </div>
                      )}
                      {t.pending && <p>{t.pending.missing}</p>}
                      {f.audits
                        .filter((a) =>
                          a.history.some(
                            (h) =>
                              h.proposal.scope === t.scope &&
                              h.proposal.topic === t.topic,
                          ),
                        )
                        .map((a, j) => (
                          <Revisions
                            key={j}
                            audit={a}
                            id={"task" + i + "-" + j}
                          />
                        ))}
                      {!f.audits.some((a) =>
                        a.history.some(
                          (h) =>
                            h.proposal.scope === t.scope &&
                            h.proposal.topic === t.topic,
                        ),
                      ) && <p>No new verdict in this snapshot.</p>}
                    </>
                  )}
                </article>
              ))}
              <details>
                <summary>
                  Eligible originals · {f.eligible_digests.length}
                </summary>
                {(
                  f.originals ||
                  f.graph.nodes.filter(
                    (n) =>
                      n.kind === "Document" &&
                      f.eligible_digests.includes(n.digest || ""),
                  )
                ).map((n) => (
                  <p key={n.id}>
                    {n.published} ·{" "}
                    <ProofButton
                      id={"doc" + n.id}
                      proof={{
                        title: "Admitted publication",
                        date: n.published,
                        url:
                          n.digest === b.meta.sha256
                            ? b.original
                            : publicUrl(n.source),
                        detail: "Document fingerprint: " + n.digest,
                      }}
                    >
                      {n.digest === b.meta.sha256
                        ? "Annual report"
                        : n.source?.split("/").pop() || "Source record"}{" "}
                      ↗
                    </ProofButton>
                  </p>
                ))}
              </details>
              {f.search_trace && (
                <details open={p.trace === "on" || undefined}>
                  <summary>
                    Discovery log · {searches.length} searches ·{" "}
                    {decisions.length} source decisions
                  </summary>
                  <p>
                    Search leads are not verified evidence. Only admitted
                    originals can support findings.
                  </p>
                  {searches.map((q, i) => (
                    <details key={i}>
                      <summary>
                        {q.query} · {q.found.length} leads
                      </summary>
                      {q.search_error && (
                        <p>Search unavailable: {q.search_error}</p>
                      )}
                      {q.found
                        .filter((u) => publicUrl(u))
                        .map((u, j) => (
                          <p key={j}>
                            <a href={u} rel="noreferrer" target="_blank">
                              {u}
                            </a>
                          </p>
                        ))}
                    </details>
                  ))}
                  <h4>Source decisions</h4>
                  {decisions.map((d, i) => (
                    <article key={i} className="ar-item">
                      <strong>{d.decision}</strong>
                      <p>
                        {publicUrl(d.url) ? (
                          <a href={d.url} target="_blank" rel="noreferrer">
                            {d.url}
                          </a>
                        ) : (
                          d.url
                        )}
                      </p>
                      {d.published && (
                        <p>
                          Publication: {d.published} · {d.origin}
                        </p>
                      )}
                      {d.date_evidence?.map((s, j) => (
                        <p key={j}>{s}</p>
                      ))}
                    </article>
                  ))}
                </details>
              )}
            </>
          )
        ) : !r ? (
          <Empty>
            No reviewed snapshot for this date. Later alerts are not included.
          </Empty>
        ) : (
          <>
            <h3>
              {r.alerts.filter((a) => a.day === b.cutoff).length} new ·{" "}
              {r.alerts.filter((a) => a.day < b.cutoff).length} carried forward
            </h3>
            <p>
              Reviewed historical mappings. These alerts were not produced by
              the fresh run.
            </p>
            {p.target && (
              <p>
                Segment: {endpoint(p.target)}{" "}
                <button onClick={() => go({ target: "" })}>Clear filter</button>
              </p>
            )}
            {p.target && !r.alerts.some((a) => a.segment === p.target) && (
              <Empty>No reviewed alerts for this segment.</Empty>
            )}
            {r.alerts
              .filter((a) => !p.target || a.segment === p.target)
              .map((a) => (
                <article className="ar-item" key={a.alert}>
                  <small>
                    {a.day === b.cutoff ? "New at cutoff" : "Carried forward"} ·
                    Detected {a.day} · Source published {a.published}
                  </small>
                  <h3>
                    {endpoint(a.product)} · {endpoint(a.segment)}
                  </h3>
                  <p>{a.interpretation}</p>
                  <ProofButton
                    id={"alert" + a.alert}
                    proof={caseProof(
                      r.evidence[a.evidence],
                      endpoint(a.product),
                    )}
                  />
                  <h4>Reported segment change</h4>
                  <p>March–August · H1 2025/26 → H1 2026/27 · EUR million</p>
                  <table>
                    <thead>
                      <tr>
                        <th>Metric</th>
                        <th>Prior</th>
                        <th>Current</th>
                        <th>Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(a.actuals).map(([k, v]) => (
                        <tr key={k}>
                          <th>{k}</th>
                          <td>{num(v.prior)}</td>
                          <td>{num(v.current)}</td>
                          <td>{delta(v.change)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <ProofButton
                    id={"metric" + a.alert}
                    proof={caseProof(
                      r.evidence[a.financial_evidence],
                      "Reported H1 performance",
                    )}
                  >
                    Half-year table ↗
                  </ProofButton>
                  <p className="ar-notice">
                    Attributable revenue: {a.attributable_revenue} ·
                    Attributable profit: {a.attributable_operating_result} ·
                    Contract fulfilment: {a.fulfillment}
                  </p>
                  <button
                    onClick={() =>
                      go({
                        view: "relationships",
                        layer: "business",
                        path: a.alert,
                        focus: a.segment,
                      })
                    }
                  >
                    Trace evidence path →
                  </button>
                  <Sensitivity s={a.scenario} />
                </article>
              ))}
            <h3>Policy comparison</h3>
            <p>Assigned task · {r.policy_task}</p>
            {Object.entries(r.policies).map(([country, v]) => (
              <div className="ar-item" key={country}>
                <strong>
                  {country} · {v.status}
                </strong>
                <p>
                  Evidence {v.published} · Effective date:{" "}
                  {v.effective || "unknown"}
                </p>
                <ProofButton
                  id={"policy" + country}
                  proof={caseProof(
                    r.evidence[v.evidence],
                    country + " policy status",
                  )}
                />
              </div>
            ))}
            {r.policy_notes.map((n, i) => (
              <p key={i}>
                {n.text}{" "}
                <ProofButton
                  id={"policy-note" + i}
                  proof={caseProof(r.evidence[n.evidence], "Policy scope")}
                />
              </p>
            ))}
            {r.tax_scenario && <Sensitivity s={r.tax_scenario} />}
          </>
        )}
      </section>
    </>
  );
}
