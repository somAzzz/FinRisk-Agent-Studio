import { useState } from "react";
import { annualProof, Empty, ProofButton, useDesk } from "./context";
import { delta, label, num, type Bundle, type Check } from "./model";
export function operating(b: Bundle) {
  return b.annual.reconciliations.find(
    (c) => c.metric === "Operatives Ergebnis",
  );
}
function contribution(c: Check) {
  const total = c.rows[c.rows.length - 1],
    diff = total.values[0] - total.values[1];
  const lead = c.rows
    .slice(0, -1)
    .filter((r) => (r.values[0] - r.values[1]) * diff > 0)
    .sort(
      (a, b) =>
        Math.abs(b.values[0] - b.values[1]) -
        Math.abs(a.values[0] - a.values[1]),
    )[0];
  return lead && diff
    ? { total, lead, pct: (100 * (lead.values[0] - lead.values[1])) / diff }
    : null;
}
export function Overview() {
  const { b, go } = useDesk(),
    c = operating(b),
    x = c?.status === "passed" && c.rows.length && contribution(c),
    check = b.annual.reconciliations;
  return (
    <>
      <section className="ar-hero">
        <span className="ar-kicker">Annual baseline · Segment performance</span>
        {x && c ? (
          <>
            <h2>
              {label(x.lead.label)} explains {x.pct.toFixed(1)}% of the net{" "}
              {c.calculated[0] < c.calculated[1] ? "decline" : "increase"} in
              operating result.
            </h2>
            <p>
              Group operating result moved from {num(x.total.values[1])} to{" "}
              {num(x.total.values[0])} {c.unit}. {label(x.lead.label)}{" "}
              contributed {delta(x.lead.values[0] - x.lead.values[1])} {c.unit}{" "}
              to that movement.
            </p>
            <ProofButton
              id="contribution"
              proof={{
                ...annualProof(
                  b,
                  "Contribution to group movement",
                  c.physical_page,
                  [x.lead.quote, x.total.quote],
                  c.printed_page,
                ),
                detail:
                  "Segment change ÷ group change × 100 = " +
                  delta(x.lead.values[0] - x.lead.values[1]) +
                  " ÷ " +
                  delta(x.total.values[0] - x.total.values[1]) +
                  " × 100 = " +
                  x.pct.toFixed(1) +
                  "%. Accounting contribution, not causal attribution.",
              }}
            >
              Inspect calculation ↗
            </ProofButton>
          </>
        ) : (
          <>
            <h2>
              {b.annual.findings[0]?.subject ||
                "Annual results ready for review"}
            </h2>
            <p>
              {b.annual.findings[0]?.assessment ||
                "Inspect the reported facts and review results below."}
            </p>
          </>
        )}
      </section>
      <SegmentTable compact />
      <div className="ar-grid">
        <section>
          <h3>Research follow-up</h3>
          {b.fresh && (
            <p>
              <button onClick={() => go({ view: "tracking", lane: "fresh" })}>
                {b.fresh.tasks.length} tracking questions →
              </button>
            </p>
          )}
          <p>
            {b.reviewed
              ? b.reviewed.alerts.length +
                " previously reviewed alerts in this snapshot."
              : "No reviewed case snapshot available at this cutoff."}
          </p>
          <button
            onClick={() =>
              go({ view: "tracking", lane: b.reviewed ? "reviewed" : "fresh" })
            }
          >
            View related alerts →
          </button>
        </section>
        <section>
          <h3>What remains unresolved</h3>
          <p>
            {b.product
              ? b.product.edges.filter((e) => e.status === "unknown").length +
                " product relationships lack a confirmed segment."
              : "Product-audit results are unavailable at this cutoff."}
          </p>
          <button
            onClick={() => go({ view: "relationships", layer: "candidates" })}
          >
            Inspect candidates →
          </button>
        </section>
      </div>
      <p className="ar-foot">
        {check.filter((v) => v.status === "passed").length} of {check.length}{" "}
        financial checks passed. These checks establish arithmetic consistency.
      </p>
    </>
  );
}
export function SegmentTable({ compact = false }: { compact?: boolean }) {
  const { b, p, go } = useDesk(),
    checks = b.annual.reconciliations.filter(
      (c) => c.metric !== "operating_result_bridge",
    ),
    c = checks.find((v) => v.metric === p.metric) || operating(b) || checks[0];
  if (!c?.rows.length)
    return <Empty>No comparable segment table was extracted.</Empty>;
  return (
    <section>
      <div className="ar-row">
        <div>
          <span className="ar-kicker">Consolidated reporting</span>
          <h3>Segment comparison</h3>
        </div>
        {!compact && (
          <label>
            Measure
            <select
              value={c.metric}
              onChange={(e) => go({ metric: e.target.value })}
            >
              {checks.map((z) => (
                <option value={z.metric} key={z.metric}>
                  {label(z.metric)}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <p>
        {label(c.metric)} · {c.unit} · Reported fiscal years
      </p>
      <div className="ar-tablewrap">
        <table>
          <thead>
            <tr>
              <th>Segment</th>
              <th>{c.periods[1]}</th>
              <th>{c.periods[0]}</th>
              <th>Change</th>
            </tr>
          </thead>
          <tbody>
            {c.rows.map((r, i) => (
              <tr
                key={i}
                className={p.segment === r.label ? "ar-selected" : ""}
              >
                <th>
                  <button
                    onClick={() => go({ view: "financials", segment: r.label })}
                  >
                    {label(r.label)}
                  </button>
                </th>
                <td>{num(r.values[1])}</td>
                <td>{num(r.values[0])}</td>
                <td>
                  <ProofButton
                    id={"seg-" + c.metric + i}
                    proof={{
                      ...annualProof(
                        b,
                        label(r.label) + " · " + label(c.metric),
                        c.physical_page,
                        r.quote,
                        c.printed_page,
                      ),
                      detail:
                        num(r.values[0]) +
                        " − " +
                        num(r.values[1]) +
                        " = " +
                        delta(r.values[0] - r.values[1]) +
                        " " +
                        c.unit,
                    }}
                  >
                    {delta(r.values[0] - r.values[1])} ↗
                  </ProofButton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {p.segment && !compact && b.segment_nodes?.[p.segment] && (
        <p>
          Selected: <strong>{label(p.segment)}</strong> ·{" "}
          <button
            onClick={() =>
              go({
                view: "tracking",
                lane: "reviewed",
                target: b.segment_nodes![p.segment],
              })
            }
          >
            View related alerts →
          </button>
        </p>
      )}
    </section>
  );
}
export function Financial() {
  const { b, p, go } = useDesk(),
    a = b.annual;
  const query = (p.q || "").toLowerCase(),
    [limit, setLimit] = useState(15);
  const rows = a.financial_rows
    .map((r, i) => ({ r, i }))
    .filter(({ r }) =>
      [r.label, label(r.label), r.section, r.physical_page]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  return (
    <>
      <SegmentTable />
      <section>
        <h3>Operating measures</h3>
        {!a.chart_rows.length && <Empty>No chart measures extracted.</Empty>}
        <div className="ar-charts">
          {a.chart_rows.map((r, i) => (
            <div key={i}>
              <h4>{label(r.metric)}</h4>
              <p>
                {r.change.decimal_value
                  ? delta(Number(r.change.decimal_value))
                  : r.change.value}
                {r.change.unit} published change
              </p>
              <table>
                <tbody>
                  {[r.change.from_year, r.change.to_year].map((y) => (
                    <tr key={y}>
                      <th>{y}</th>
                      <td>
                        <span
                          className="ar-bar"
                          style={{
                            width:
                              Math.max(
                                1,
                                (Math.abs(+r.decimal_values[y]) /
                                  Math.max(
                                    ...Object.values(r.decimal_values).map(
                                      (v) => Math.abs(+v),
                                    ),
                                    1,
                                  )) *
                                  75,
                              ) + "px",
                          }}
                        />
                        {num(Number(r.decimal_values[y]))}{" "}
                        {r.unit === "Mio. t" ? "million tonnes" : r.unit}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ProofButton
                id={"chart" + i}
                proof={{
                  ...annualProof(
                    b,
                    label(r.metric),
                    r.physical_page,
                    [
                      r.metric,
                      ...[r.change.from_year, r.change.to_year].map(
                        (y) => y + ": " + r.values[y] + " " + r.unit,
                      ),
                      r.change.value + " " + r.change.unit,
                    ],
                    r.printed_page,
                  ),
                  detail:
                    r.chart_id +
                    " · " +
                    r.method +
                    " · Published change " +
                    r.change.value +
                    " " +
                    r.change.unit,
                }}
              >
                Chart source ↗
              </ProofButton>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h3>Profit bridge</h3>
        {a.reconciliations
          .filter((c) => c.metric === "operating_result_bridge")
          .flatMap((c) =>
            c.rows.map((r, i) => (
              <p key={i}>
                <ProofButton
                  id={"bridge" + i}
                  proof={annualProof(
                    b,
                    label(r.label),
                    c.physical_page,
                    r.quote,
                    c.printed_page,
                  )}
                >
                  {label(r.label)} ↗
                </ProofButton>{" "}
                {r.values
                  .map((v, j) => c.periods[j] + ": " + num(v))
                  .join(" / ")}{" "}
                {c.unit}
              </p>
            )),
          )}
        {!a.reconciliations.some(
          (c) => c.metric === "operating_result_bridge",
        ) && <Empty>No operating result bridge extracted.</Empty>}
      </section>
      <section>
        <h3>Cash flow & working capital</h3>
        <p>
          Published balances and cash flows, shown at their disclosed scope.
        </p>
        {a.financial_rows.map(
          (r, i) =>
            /cash\s?flow|working capital/i.test(r.label) && (
              <p key={i}>
                <ProofButton
                  id={"cash" + i}
                  proof={annualProof(
                    b,
                    label(r.label),
                    r.physical_page,
                    r.quote,
                    r.printed_page,
                  )}
                >
                  {label(r.label)} · {r.section} ↗
                </ProofButton>{" "}
                {r.values
                  .map((v, j) => r.periods[j] + ": " + num(v))
                  .join(" / ")}{" "}
                {r.unit}
              </p>
            ),
        )}
        {!a.financial_rows.some((r) =>
          /cash\s?flow|working capital/i.test(r.label),
        ) && <Empty>No matching source rows.</Empty>}
      </section>
      <section>
        <h3>Reconciliation checks</h3>
        {a.reconciliations.map((c, i) => (
          <p key={i}>
            <ProofButton
              id={"check" + i}
              proof={annualProof(
                b,
                label(c.metric),
                c.physical_page,
                c.rows.map((r) => r.quote),
                c.printed_page,
              )}
            >
              {label(c.metric)} · {c.status} ↗
            </ProofButton>{" "}
            <small>
              {c.calculated.join(" / ")} {c.unit}
            </small>
          </p>
        ))}
      </section>
      <section>
        <div className="ar-row">
          <h3>Financial facts</h3>
          <label>
            Find a metric, section or page
            <input
              value={p.q || ""}
              onChange={(e) => {
                setLimit(15);
                go({ q: e.target.value });
              }}
            />
          </label>
        </div>
        <p>
          {rows.length} source rows · repeated disclosures are shown separately.
        </p>
        <div className="ar-tablewrap">
          <table>
            <thead>
              <tr>
                <th>Metric / section</th>
                <th>Period and value</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {rows
                .slice(0, p.proof?.startsWith("fact") ? undefined : limit)
                .map(({ r, i }) => (
                  <tr key={i}>
                    <th>
                      {label(r.label)}
                      <small>{r.section}</small>
                    </th>
                    <td>
                      {r.values.map((v, j) => (
                        <small key={j}>
                          {r.periods[j]} · {num(v)} {r.unit}
                        </small>
                      ))}
                    </td>
                    <td>
                      <ProofButton
                        id={"fact" + i}
                        proof={annualProof(
                          b,
                          label(r.label),
                          r.physical_page,
                          r.quote,
                          r.printed_page,
                        )}
                      >
                        p. {r.physical_page} ↗
                      </ProofButton>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        {limit < rows.length && (
          <button onClick={() => setLimit(limit + 25)}>Show more facts</button>
        )}
      </section>
    </>
  );
}
