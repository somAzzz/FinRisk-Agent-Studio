import { lazy, Suspense } from "react";
import {
  annualProof,
  caseProof,
  cited,
  Empty,
  ProofButton,
  useDesk,
} from "./context";
import { endpoint, pretty } from "./model";
const Canvas = lazy(() => import("./RelationCanvas"));
function Select({
  title,
  v,
  opts,
  change,
}: {
  title: string;
  v: string;
  opts: string[];
  change: (v: string) => void;
}) {
  return (
    <label>
      {title}
      <select value={v} onChange={(e) => change(e.target.value)}>
        <option value="">Any</option>
        {opts.map((o) => (
          <option key={o} value={o}>
            {pretty(o)}
          </option>
        ))}
      </select>
    </label>
  );
}
export function Relations() {
  const { b, p, go } = useDesk(),
    r = b.reviewed,
    layer = p.layer || (b.fresh || r ? "business" : "annual");
  const allowed = (r?.edges || [])
    .map((e, idx) => ({ ...e, idx }))
    .filter(
      (e) =>
        e.published <= b.cutoff &&
        (p.infer === "on" || e.provenance !== "model_inference"),
    );
  const path = r?.alerts.find((a) => a.alert === p.path),
    focus = p.focus || r?.nodes.find((n) => n.kind === "Segment")?.id || "";
  const touches = (e: (typeof allowed)[number], id: string) =>
    e.subject === id || e.object === id;
  const names = Object.fromEntries(
    (r?.nodes || []).map((n) => [
      n.id,
      n.kind === "Alert reference"
        ? endpoint(
            r?.alerts.find((a) => "Alert reference/" + a.alert === n.id)
              ?.product || n.name,
          ) + " alert"
        : n.kind === "Scenario"
          ? "Illustrative scenario"
          : n.kind === "Metric"
            ? n.name.split("/").pop() +
              " · " +
              n.period +
              " (" +
              (Number(n.change) > 0 ? "+" : "") +
              n.change +
              " " +
              n.unit +
              ")"
            : n.name,
    ]),
  );
  const edges = allowed.filter(
    (e) =>
      (path
        ? (e.subject === "Alert reference/" + path.alert &&
            e.relation === "CONCERNS") ||
          (e.subject === path.segment &&
            (e.object === path.product || e.relation === "REPORTED"))
        : touches(e, focus)) &&
      (!p.kind ||
        [e.subject, e.object].some((id) => id.split("/")[0] === p.kind)) &&
      (!p.role || e.relation === p.role) &&
      (!p.origin || e.provenance === p.origin),
  );
  const candidates = (b.product?.edges || [])
    .map((e, i) => ({ e, i }))
    .filter(
      ({ e }) =>
        e.status === "unknown" &&
        [e.subject, e.object, e.quote]
          .join(" ")
          .toLowerCase()
          .includes((p.search || "").toLowerCase()),
    );
  const flows = b.annual.supply_chain_edges.map((edge, idx) => ({
    subject: edge.from_node,
    object: edge.to_node,
    relation: edge.relationship,
    idx,
    evidence: "flow" + idx + "-0",
    published: edge.evidence[0]?.published_at || "",
    provenance: edge.evidence.every((c) => c.source_id === "annual")
      ? "annual_report_disclosure"
      : "cited_disclosure",
  }));
  const flowFocus = p.entity || flows[0]?.subject;
  const flowEdges = flows.filter(
    (e) => e.subject === flowFocus || e.object === flowFocus,
  );
  const flowNames = Object.fromEntries(
    flows.flatMap((e) => [
      [e.subject, e.subject],
      [e.object, e.object],
    ]),
  );
  const focusNode = (id: string) => go({ focus: id, path: "", proof: "" });
  return (
    <section>
      <span className="ar-kicker">Provenance & scope</span>
      <h2>Relationships</h2>
      <div className="ar-chips">
        {[
          ["business", "Reviewed relationships"],
          ["annual", "Annual disclosures"],
          ["candidates", "Unconfirmed candidates"],
        ].map(([k, v]) => (
          <button
            key={k}
            aria-pressed={k === layer}
            onClick={() => go({ layer: k, path: "", proof: "" })}
          >
            {v}
          </button>
        ))}
      </div>
      {layer === "candidates" ? (
        <>
          <h3>Unconfirmed segment assignments</h3>
          {!b.product ? (
            <Empty>Product audit not available for this run and cutoff.</Empty>
          ) : (
            <>
              <p>
                {b.product.edges.filter((e) => e.status === "unknown").length}{" "}
                candidate relationships ·{" "}
                {b.product.edges.filter((e) => e.status === "supported").length}{" "}
                confirmed.{" "}
                {b.product.note.page == null
                  ? "The extractor did not locate the formal segment note."
                  : ""}{" "}
                These candidates create no verified paths.
              </p>
              <label>
                Find product or proposed segment
                <input
                  value={p.search || ""}
                  onChange={(e) => go({ search: e.target.value })}
                />
              </label>
              {p.search && (
                <p role="status">{candidates.length} matching candidates</p>
              )}
              {candidates.map(({ e, i }) => (
                <article key={i} className="ar-item">
                  <strong>{e.object}</strong>
                  <p>Proposed segment: {e.subject} · Unconfirmed</p>
                  <p>{e.review}</p>
                  <ProofButton
                    id={"candidate" + i}
                    proof={annualProof(b, e.object, e.page, e.quote)}
                  >
                    Catalogue mention · p. {e.page} ↗
                  </ProofButton>
                </article>
              ))}
            </>
          )}
        </>
      ) : layer === "annual" ? (
        <>
          <h3>Relationships extracted from the report analysis</h3>
          {flows.length > 0 && (
            <>
              <div className="ar-tools">
                <label>
                  Explore entity
                  <select
                    value={flowFocus}
                    onChange={(e) => go({ entity: e.target.value })}
                  >
                    {Object.keys(flowNames).map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                  </select>
                </label>
                <button
                  aria-pressed={p.canvas === "on"}
                  onClick={() => go({ canvas: p.canvas === "on" ? "" : "on" })}
                >
                  {p.canvas === "on" ? "Hide graph" : "Show graph"}
                </button>
              </div>
              <p>
                {flowEdges.length} in focus / {flows.length} total. Each arrow
                retains the wording and scope of its cited finding. Customer
                classes do not identify individual buyers.
              </p>
              {p.canvas === "on" && (
                <Suspense fallback={<p>Loading graph…</p>}>
                  <Canvas
                    key={flowFocus}
                    edges={flowEdges}
                    names={flowNames}
                    focus={flowFocus}
                    open={(i) => go({ proof: "flow" + i + "-0" })}
                    expand={(n) => go({ entity: n })}
                  />
                </Suspense>
              )}
            </>
          )}
          {b.annual.supply_chain_edges.map(
            (e, i) =>
              [e.from_node, e.to_node].includes(flowFocus) && (
                <article key={i} className="ar-item">
                  <strong>
                    {e.from_node} · {pretty(e.relationship)} · {e.to_node}
                  </strong>
                  <p>Contract fulfilment: {e.fulfillment}</p>
                  {e.evidence.map((c, j) => (
                    <ProofButton
                      id={"flow" + i + "-" + j}
                      key={j}
                      proof={cited(b, e.from_node, c)}
                    />
                  ))}
                </article>
              ),
          )}
          {!b.annual.supply_chain_edges.length && (
            <Empty>No annual-only links available at this cutoff.</Empty>
          )}
        </>
      ) : !r ? (
        <Empty>No reviewed snapshot for this date.</Empty>
      ) : (
        <>
          <div className="ar-row">
            <div>
              <h3>{path ? "Alert evidence path" : "Business relationships"}</h3>
              <p>
                {r.nodes.length} nodes · {r.edges.length} stored links ·{" "}
                {
                  r.edges.filter((e) => e.provenance === "model_inference")
                    .length
                }{" "}
                model inferences
              </p>
            </div>
            <label>
              Focus on
              <select value={focus} onChange={(e) => focusNode(e.target.value)}>
                {r.nodes.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.kind} · {names[n.id]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {path && (
            <p className="ar-notice">
              {endpoint(path.product)} alert · {endpoint(path.segment)} reported
              an operating-result change of{" "}
              {path.actuals["Operating result"]?.change > 0 ? "+" : ""}
              {path.actuals["Operating result"]?.change} EURm. Attributable
              impact: {path.attributable_operating_result}. Fulfilment:{" "}
              {path.fulfillment}.{" "}
              <button onClick={() => go({ path: "" })}>Exit path</button>
            </p>
          )}
          <div className="ar-tools">
            <Select
              title="Entity type"
              v={p.kind || ""}
              opts={[...new Set(r.nodes.map((n) => n.kind))]}
              change={(v) => go({ kind: v })}
            />
            <Select
              title="Relationship"
              v={p.role || ""}
              opts={[...new Set(allowed.map((e) => e.relation))]}
              change={(v) => go({ role: v })}
            />
            <Select
              title="Origin"
              v={p.origin || ""}
              opts={[...new Set(allowed.map((e) => e.provenance))]}
              change={(v) => go({ origin: v })}
            />
            <label className="ar-inline">
              <input
                type="checkbox"
                checked={p.infer === "on"}
                onChange={(e) =>
                  go({
                    infer: e.target.checked ? "on" : "",
                    origin: "",
                    role: "",
                  })
                }
              />{" "}
              Include model inferences
            </label>
          </div>
          <div className="ar-row">
            <p>
              {edges.length} links in focus · select a neighbour to explore its
              links.
            </p>
            <button
              aria-pressed={p.canvas === "on"}
              onClick={() => go({ canvas: p.canvas === "on" ? "" : "on" })}
            >
              {p.canvas === "on" ? "Hide graph" : "Show graph"}
            </button>
          </div>
          {edges.length === 0 && (
            <Empty>
              No supported paths match this selection. Exposure may still exist.
            </Empty>
          )}
          {p.canvas === "on" && edges.length > 0 && (
            <Suspense fallback={<p>Loading graph…</p>}>
              <Canvas
                key={focus + edges.map((e) => e.idx).join(",")}
                edges={edges}
                names={names}
                focus={focus}
                open={(i) => go({ proof: "edge" + i })}
                expand={focusNode}
              />
            </Suspense>
          )}
          <div className="ar-links" aria-label="Relationship path list">
            {edges.map((e) => (
              <article key={e.idx} className="ar-item">
                <small>
                  {pretty(e.provenance)} · {e.published}
                </small>
                <div>
                  <strong>{names[e.subject]}</strong>{" "}
                  <span className="ar-verb">
                    {pretty(e.relation).toLowerCase()} →
                  </span>{" "}
                  <strong>{names[e.object]}</strong>
                </div>
                <ProofButton
                  id={"edge" + e.idx}
                  proof={{
                    ...caseProof(
                      r.evidence[e.evidence],
                      names[e.subject] +
                        " · " +
                        pretty(e.relation).toLowerCase() +
                        " · " +
                        names[e.object],
                    ),
                    origin: pretty(e.provenance),
                  }}
                />{" "}
                <button
                  onClick={() =>
                    focusNode(e.subject === focus ? e.object : e.subject)
                  }
                >
                  Explore neighbour (
                  {
                    allowed.filter((x) =>
                      touches(x, e.subject === focus ? e.object : e.subject),
                    ).length
                  }
                  )
                </button>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
