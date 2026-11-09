import {
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import {
  ArrowUpRight,
  Archive,
  BookOpen,
  CalendarDays,
  FileText,
  Library,
} from "lucide-react";
import { api, describeApiError } from "../api";
import { Workspace, Empty, type Params } from "./context";
import {
  indexRoute,
  reportRoute,
  sample,
  type Bundle,
  type Entry,
} from "./model";
import { Overview, Financial } from "./Financial";
import { Relations } from "./Relations";
import { Evidence, Tracking } from "./Review";
import { filingHash, rememberFiling, lastFiling } from "./navigation";
import { issuerRoute } from "./company";
import { CompanyWorkspaceNav } from "../components/CompanyWorkspaceNav";
import "./annual.css";
const sections = [
  { id: "overview", label: "Overview" },
  { id: "financials", label: "Financials" },
  { id: "relationships", label: "Supply chain" },
  { id: "tracking", label: "Risks & tracking" },
  { id: "evidence", label: "Evidence & review" },
  { id: "reader", label: "Report reader" },
];
function subscribe(cb: () => void) {
  window.addEventListener("hashchange", cb);
  window.addEventListener("popstate", cb);
  return () => {
    window.removeEventListener("hashchange", cb);
    window.removeEventListener("popstate", cb);
  };
}
function rich(text: string, follow: (url: string) => void): ReactNode[] {
  return text
    .split(/(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`)/g)
    .map((t, i) => {
      const link = t.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      return link ? (
        /^https?:\/\//.test(link[2]) ? (
          <a key={i} href={link[2]} rel="noreferrer" target="_blank">
            {link[1]} ↗
          </a>
        ) : (
          <button key={i} onClick={() => follow(link[2])}>
            {link[1]}
          </button>
        )
      ) : t.startsWith("**") ? (
        <strong key={i}>{t.slice(2, -2)}</strong>
      ) : t.startsWith("`") ? (
        <code key={i}>{t.slice(1, -1)}</code>
      ) : (
        t
      );
    });
}
function Reader({ b, go }: { b: Bundle; go: (p: Params) => void }) {
  if (!b.narrative)
    return (
      <Empty>
        No reviewed analyst synthesis for this run and date. The annual
        disclosures remain available.
      </Empty>
    );
  const follow = (u: string) => {
    if (u.startsWith("replay/"))
      go({
        view: "tracking",
        lane: "reviewed",
        day: u.includes("10-08") ? "2026-10-08" : "2026-11-08",
      });
    else if (u.endsWith("discovery.json"))
      go({ view: "tracking", lane: "fresh", trace: "on" });
    else if (u.startsWith("fresh-tracking/"))
      go({ view: "tracking", lane: "fresh", day: "2026-10-08" });
    else if (u.includes("product-audit"))
      go({ view: "relationships", layer: "candidates" });
    else go({ view: u.includes("annual.json") ? "financials" : "evidence" });
  };
  const lines = b.narrative.split("\n"),
    out: ReactNode[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    if (line.startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        if (!/^\|[-: |]+\|$/.test(lines[i]))
          rows.push(
            lines[i]
              .slice(1, -1)
              .split("|")
              .map((s) => s.trim()),
          );
        i++;
      }
      i--;
      out.push(
        <div key={i} className="ar-tablewrap">
          <table>
            <thead>
              <tr>
                {rows[0].map((s, k) => (
                  <th key={k}>{rich(s, follow)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(1).map((rr, j) => (
                <tr key={j}>
                  {rr.map((s, k) => (
                    <td key={k}>{rich(s, follow)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
    } else
      out.push(
        line.startsWith("# ") ? (
          <h2 key={i}>{line.slice(2)}</h2>
        ) : line.startsWith("## ") ? (
          <h3 key={i}>{line.slice(3)}</h3>
        ) : (
          <p key={i}>{rich(line.replace(/^- /, "• "), follow)}</p>
        ),
      );
  }
  return (
    <section className="ar-reader">
      <span className="ar-kicker">
        Analyst synthesis · Includes separately checked policy sources
      </span>
      {out}
    </section>
  );
}
export default function AnnualWorkspace({
  staticMode,
  start,
  openGeneral,
}: {
  staticMode: boolean;
  start: () => void;
  openGeneral?: () => void;
}) {
  const hash = useSyncExternalStore(subscribe, () => location.hash),
    [path, query = ""] = hash.split("?"),
    id = path.split("/")[4] || "",
    p = Object.fromEntries(new URLSearchParams(query)),
    day = p.day || "";
  const [list, setList] = useState<Entry[] | null>(null),
    [load, setLoad] = useState<{ key: string; b: Bundle } | null>(null),
    [failure, setFailure] = useState<{ key: string; msg: string } | null>(null),
    [retry, setRetry] = useState(0);
  const key = id + "@" + day;
  useEffect(() => {
    let live = true;
    setFailure(null);
    const task = !id
      ? (staticMode ? sample<Entry[]>("index.json") : api.annualLibrary()).then(
          (v) => {
            if (live) setList(v);
          },
        )
      : (staticMode
          ? sample<Bundle>(
              encodeURIComponent(id) +
                "/" +
                encodeURIComponent(day || "latest") +
                ".json",
            )
          : api.savedAnnual(id, day)
        ).then((b) => {
          if (live) setLoad({ key, b });
        });
    task.catch((e) => {
      if (live)
        setFailure({ key, msg: describeApiError(e, "Saved annual report") });
    });
    return () => {
      live = false;
    };
  }, [id, day, staticMode, retry, key]);
  const b = load?.key === key ? load.b : null,
    legacyUnavailable =
      p.workspace === "company" && ["valuation", "management"].includes(p.view),
    view =
      legacyUnavailable || sections.some((s) => s.id === p.view)
        ? p.view
        : "overview";
  useEffect(() => {
    if (b) rememberFiling(hash);
  }, [hash, b]);
  function go(v: Params, reset = false) {
    const next = new URLSearchParams(reset ? {} : p);
    if (v.view && v.view !== view) {
      for (const k of [...next.keys()])
        if (
          ![
            "day",
            "lane",
            "segment",
            "workspace",
            "from",
            "companyDay",
          ].includes(k)
        )
          next.delete(k);
    }
    if (v.day && v.day !== day) {
      next.delete("proof");
      if (p.proof) next.set("notice", "source");
      else next.delete("notice");
    }
    for (const [k, val] of Object.entries(v)) {
      if (val) next.set(k, val);
      else next.delete(k);
    }
    const h = reportRoute(id) + (next.size ? "?" + next.toString() : "");
    if (h === hash) return;
    if ("q" in v || "search" in v) history.replaceState(null, "", h);
    else history.pushState(v.proof ? { annualProof: true } : null, "", h);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    if (v.view && v.view !== view)
      document.getElementById("ar-heading")?.scrollIntoView({ block: "start" });
  }
  const error =
    failure?.key === key ? (
      <div role="alert" className="ar-empty">
        {failure.msg}{" "}
        <button onClick={() => setRetry((n) => n + 1)}>Retry</button>
      </div>
    ) : null;
  if (!id)
    return (
      <div className="ar">
        <header className="ar-mast">
          <div>
            <span className="ar-kicker">
              <Library size={16} /> Company research
            </span>
            <h1>Annual report library</h1>
            {openGeneral && (
              <button onClick={openGeneral}>
                Open general company research
              </button>
            )}
            {lastFiling() && (
              <a href={lastFiling()!}>Resume last annual report →</a>
            )}
            <p>
              Reopen a saved analysis, inspect the accounts and trace the
              evidence available at each cutoff.
            </p>
          </div>
          {!staticMode && (
            <button className="ar-primary" onClick={start}>
              Analyze a new report
            </button>
          )}
        </header>
        {error ||
          (!list ? (
            <p role="status">Loading saved reports…</p>
          ) : !list.length ? (
            <Empty>
              No saved annual reports. Start a new analysis to add the first
              one.
            </Empty>
          ) : (
            <section>
              <h2>Verified company workspaces</h2>
              {[
                ...new Map(
                  list
                    .filter((x) => x.issuer?.company_id)
                    .map((x) => [x.issuer!.company_id!, x.company]),
                ).entries(),
              ].map(([id, name]) => (
                <p key={id}>
                  <a href={issuerRoute(id)}>{name} · Across fiscal years →</a>
                </p>
              ))}
              <h2>Saved filings</h2>
              {list.map((x) => (
                <a
                  className="ar-library-entry"
                  href={reportRoute(x.id)}
                  key={x.id}
                >
                  <FileText size={28} />
                  <div>
                    <small>
                      {staticMode ? "Archived sample · " : ""}
                      {x.period}
                    </small>
                    <h3>{x.company}</h3>
                    <p>
                      {x.pages} pages · Published {x.published || "unknown"} ·{" "}
                      {x.lanes.join(" / ")}
                    </p>
                  </div>
                  <span>
                    As of {x.as_of} <ArrowUpRight size={16} />
                  </span>
                </a>
              ))}
            </section>
          ))}
      </div>
    );
  return (
    <div className="ar">
      <a className="ar-back" href={indexRoute}>
        ← Annual report library
      </a>
      {error ||
        (!b ? (
          <p role="status">Loading saved snapshot…</p>
        ) : (
          <Workspace.Provider value={{ b, p, go }}>
            {p.workspace === "company" && (
              <a className="ar-back" href={filingHash(hash)}>
                Return to annual report →
              </a>
            )}
            <header className="ar-mast" id="ar-heading">
              <div>
                <span className="ar-kicker">
                  <BookOpen size={16} />{" "}
                  {staticMode ? "Archived sample" : "Company research"} · Annual
                  report
                </span>
                <h1>{b.meta.company}</h1>
                {b.meta.issuer?.company_id ? (
                  <a
                    href={issuerRoute(
                      b.meta.issuer.company_id,
                      /^\d{4}-\d{2}-\d{2}$/.test(p.companyDay || "")
                        ? p.companyDay
                        : b.cutoff,
                    )}
                  >
                    Company workspace · Compare fiscal years →
                  </a>
                ) : (
                  <p>
                    Company identity unverified · This filing is not merged.
                  </p>
                )}
                <p>
                  {b.meta.period} <span> / </span> {b.meta.pages} pages{" "}
                  <span> / </span> Published {b.meta.published || "unknown"}
                </p>
              </div>
              <label>
                <span>
                  <CalendarDays size={15} /> Evidence cutoff
                </span>
                <select
                  value={b.cutoff}
                  onChange={(e) => go({ day: e.target.value })}
                >
                  {b.meta.dates.map((d) => (
                    <option key={d}>{d}</option>
                  ))}
                </select>
              </label>
            </header>
            <CompanyWorkspaceNav
              company={b.meta.company}
              sections={sections}
              active={view}
              onSelect={(v) => go({ view: v })}
              className="ar-tabs"
            />
            {p.notice === "source" && (
              <p role="status" className="ar-foot">
                Source drawer closed when the cutoff changed. Open an eligible
                source below.
              </p>
            )}
            {((p.path && !b.reviewed?.alerts.some((a) => a.alert === p.path)) ||
              (p.task && !b.fresh?.tasks.some((t) => t.id === p.task)) ||
              (p.claim && !b.annual.fact_reviews[Number(p.claim)]) ||
              (p.focus &&
                !b.reviewed?.nodes.some((n) => n.id === p.focus))) && (
              <p role="status" className="ar-foot">
                The selected item is unavailable at this cutoff. Return to its
                original date to inspect it.
              </p>
            )}
            {legacyUnavailable ? (
              <section>
                <h2>{view === "valuation" ? "Valuation" : "Management"}</h2>
                <Empty>
                  {view === "valuation"
                    ? "No company valuation is linked to this filing at this cutoff. Exposure scenarios are available in tracking when disclosed."
                    : "No management transcript comparison is linked to this filing at this cutoff."}
                </Empty>
                <button
                  onClick={() =>
                    go({ view: view === "valuation" ? "tracking" : "evidence" })
                  }
                >
                  {view === "valuation"
                    ? "Inspect tracking and scenarios"
                    : "Inspect filing evidence"}{" "}
                  →
                </button>
              </section>
            ) : view === "overview" ? (
              <Overview />
            ) : view === "financials" ? (
              <Financial />
            ) : view === "relationships" ? (
              <Relations />
            ) : view === "tracking" ? (
              <Tracking canInvestigate={!staticMode} />
            ) : view === "evidence" ? (
              <Evidence />
            ) : (
              <Reader b={b} go={go} />
            )}
            <footer>
              <Archive size={15} /> Saved research · {b.cutoff}{" "}
              <button
                onClick={() => {
                  const u = URL.createObjectURL(
                    new Blob([JSON.stringify(b, null, 2)], {
                      type: "application/json",
                    }),
                  );
                  const a = document.createElement("a");
                  a.href = u;
                  a.download = b.meta.id + "-" + b.cutoff + ".json";
                  a.click();
                  setTimeout(() => URL.revokeObjectURL(u), 500);
                }}
              >
                Download this snapshot
              </button>
            </footer>
          </Workspace.Provider>
        ))}
    </div>
  );
}
