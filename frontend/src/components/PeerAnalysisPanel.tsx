import { useEffect, useMemo, useState } from "react";
import { api, describeApiError } from "../api";
import type { PeerAnalysisResponse, PeerCandidate, PeerGroup } from "../types";

const parseTickers = (value: string) => Array.from(new Set(
  value.split(",").map((item) => item.toUpperCase().trim()).filter(Boolean),
));

export function PeerAnalysisPanel() {
  const [groups, setGroups] = useState<PeerGroup[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [name, setName] = useState("");
  const [baseTicker, setBaseTicker] = useState("");
  const [memberText, setMemberText] = useState("");
  const [industry, setIndustry] = useState<PeerGroup["industry_template"]>("general");
  const [metrics, setMetrics] = useState("revenue,gross_margin,free_cash_flow");
  const [valuationInputs, setValuationInputs] = useState("[]");
  const [analysis, setAnalysis] = useState<PeerAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [candidates, setCandidates] = useState<PeerCandidate[]>([]);
  const [deleteArmed, setDeleteArmed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const selected = useMemo(
    () => groups.find((group) => group.peer_group_id === selectedId) ?? null,
    [groups, selectedId],
  );

  const loadGroups = async () => {
    try {
      const next = await api.listPeerGroups();
      setGroups(next);
      setSelectedId((current) => current || next[0]?.peer_group_id || "");
      setError(null);
    } catch (nextError) {
      setError(describeApiError(nextError, "Peer groups"));
    }
  };

  useEffect(() => { void loadGroups(); }, []);

  const createGroup = async () => {
    const tickers = parseTickers(memberText);
    const base = baseTicker.toUpperCase().trim();
    if (!name.trim() || !base || tickers.length < 2 || !tickers.includes(base)) {
      setError("Provide a name, at least two unique members, and include the base ticker.");
      return;
    }
    setBusy(true);
    try {
      const group = await api.createPeerGroup({
        name: name.trim(),
        base_ticker: base,
        members: tickers.map((ticker) => ({
          ticker,
          inclusion_reason: ticker === base ? "Base company" : "Analyst-confirmed comparable company",
          source: "user",
          confirmed_by_user: true,
        })),
        industry_template: industry,
        currency_policy: "no_conversion",
        fiscal_period_policy: "calendarized_ttm",
        user_notes: null,
      });
      setGroups((current) => [group, ...current]);
      setSelectedId(group.peer_group_id);
      setName("");
      setBaseTicker("");
      setMemberText("");
      setError(null);
      setNotice("Peer group saved.");
    } catch {
      setError("Peer group could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const deleteGroup = async () => {
    if (!selected) return;
    if (!deleteArmed) {
      setDeleteArmed(true);
      setNotice("Select Delete peer group again to confirm. Saved snapshots are not deleted.");
      return;
    }
    setBusy(true);
    try {
      await api.deletePeerGroup(selected.peer_group_id);
      const remaining = groups.filter((group) => group.peer_group_id !== selected.peer_group_id);
      setGroups(remaining);
      setSelectedId(remaining[0]?.peer_group_id ?? "");
      setAnalysis(null);
      setCandidates([]);
      setDeleteArmed(false);
      setNotice("Peer group deleted. Research snapshots were preserved.");
      setError(null);
    } catch (nextError) {
      setError(describeApiError(nextError, "Peer group"));
    } finally {
      setBusy(false);
    }
  };

  const compare = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const valuations = JSON.parse(valuationInputs) as unknown;
      if (!Array.isArray(valuations)) throw new Error("valuation input must be an array");
      const histories = await Promise.all(
        selected.members.map((member) => api.listResearchSnapshots(member.ticker)),
      );
      const latest = histories.flatMap((history) => history.length ? [history[0]] : []);
      if (latest.length < 2) throw new Error("not enough snapshots");
      setAnalysis(await api.analyzePeerGroup(selected.peer_group_id, {
        snapshot_ids: latest.map((snapshot) => snapshot.snapshot_id),
        metrics: metrics.split(",").map((item) => item.trim()).filter(Boolean),
        period_kind: selected.fiscal_period_policy === "latest_fy" ? "annual" : "ttm",
        valuations,
      }));
      setError(null);
    } catch {
      setError("At least two confirmed peers need compatible research snapshots.");
    } finally {
      setBusy(false);
    }
  };

  const suggestCandidates = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      setCandidates(await api.suggestPeerCandidates(selected.peer_group_id));
      setError(null);
    } catch {
      setError("SEC SIC peer candidates could not be loaded from the Watchlist.");
    } finally {
      setBusy(false);
    }
  };

  const confirmCandidate = async (candidate: PeerCandidate) => {
    if (!selected || selected.members.some((member) => member.ticker === candidate.ticker)) return;
    setBusy(true);
    try {
      const updated = await api.updatePeerGroup(selected.peer_group_id, {
        name: selected.name,
        base_ticker: selected.base_ticker,
        industry_template: selected.industry_template,
        currency_policy: selected.currency_policy,
        fiscal_period_policy: selected.fiscal_period_policy,
        user_notes: selected.user_notes,
        members: [
          ...selected.members,
          {
            ticker: candidate.ticker,
            inclusion_reason: candidate.inclusion_reason,
            source: "suggested",
            confirmed_by_user: true,
          },
        ],
      });
      setGroups((current) => current.map((group) => (
        group.peer_group_id === updated.peer_group_id ? updated : group
      )));
      setCandidates((current) => current.filter((item) => item.ticker !== candidate.ticker));
      setError(null);
    } catch {
      setError("Peer candidate could not be confirmed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="peer-analysis" aria-labelledby="peer-analysis-title">
      <header><div><span className="research-eyebrow">Comparable-company workspace</span><h3 id="peer-analysis-title">Peer analysis</h3></div></header>
      <div className="peer-analysis-controls">
        <label>Saved group<select aria-label="Saved peer group" value={selectedId} onChange={(event) => { setSelectedId(event.target.value); setAnalysis(null); setDeleteArmed(false); setNotice(null); }}><option value="">Select a group</option>{groups.map((group) => <option key={group.peer_group_id} value={group.peer_group_id}>{group.name}</option>)}</select></label>
        <label>Metrics<input aria-label="Peer comparison metrics" value={metrics} onChange={(event) => setMetrics(event.target.value)} /></label>
        <button className="primary" type="button" disabled={!selected || busy} onClick={() => void compare()}>Compare peers</button>
        <button className="ghost danger" type="button" disabled={!selected || busy} onClick={() => void deleteGroup()}>{deleteArmed ? "Confirm delete peer group" : "Delete peer group"}</button>
      </div>
      {notice ? <p className="operation-notice" role="status">{notice}</p> : null}
      <details className="cycle-details"><summary>Optional explicit valuation inputs</summary><textarea aria-label="Peer valuation inputs" value={valuationInputs} onChange={(event) => setValuationInputs(event.target.value)} placeholder='[{"ticker":"NVDA","method":"pe","share_price":100,"diluted_shares":10,"earnings":50,"period":"TTM"}]' /><p className="muted">JSON array using P/E, EV/EBITDA or FCF-yield inputs. Values are never inferred from market data.</p></details>
      {selected ? <div className="peer-group-summary"><strong>{selected.base_ticker} · {selected.industry_template}</strong><span>{selected.fiscal_period_policy} · {selected.currency_policy}</span><ul>{selected.members.map((member) => <li key={member.ticker}><b>{member.ticker}</b> — {member.inclusion_reason}</li>)}</ul><button className="ghost" type="button" disabled={busy} onClick={() => void suggestCandidates()}>Suggest SEC SIC peers from Watchlist</button></div> : null}
      {candidates.length ? <div className="peer-candidates"><strong>Unconfirmed candidates</strong>{candidates.map((candidate) => <article key={candidate.ticker}><div><b>{candidate.ticker}</b><span>{candidate.similarity}</span><p>{candidate.inclusion_reason}</p></div><button className="ghost" type="button" disabled={busy} onClick={() => void confirmCandidate(candidate)}>Confirm peer</button></article>)}</div> : null}
      <details className="cycle-details"><summary>Create an analyst-confirmed peer group</summary><div className="peer-analysis-controls"><label>Name<input aria-label="Peer group name" value={name} onChange={(event) => setName(event.target.value)} /></label><label>Base ticker<input aria-label="Peer group base ticker" value={baseTicker} onChange={(event) => setBaseTicker(event.target.value)} /></label><label>Members<input aria-label="Peer group members" value={memberText} onChange={(event) => setMemberText(event.target.value)} placeholder="NVDA, AMD, INTC" /></label><label>Industry<select aria-label="Peer group industry" value={industry} onChange={(event) => setIndustry(event.target.value as PeerGroup["industry_template"])}>{["general", "bank", "saas", "semiconductor", "energy", "biotech"].map((item) => <option key={item}>{item}</option>)}</select></label><button className="ghost" type="button" disabled={busy} onClick={() => void createGroup()}>Save group</button></div><p className="muted">Suggested members cannot be persisted until confirmed; this form records every member as an analyst decision with an inclusion reason.</p></details>
      {error ? <p className="journal-error">{error}</p> : null}
      {analysis ? <div className="peer-analysis-results"><div className="table-scroll"><table className="research-table"><thead><tr><th>Company</th><th>Metric</th><th>Value</th><th>Freshness</th><th>Lineage</th><th>Status</th></tr></thead><tbody>{analysis.financials.values.map((value) => <tr key={`${value.ticker}-${value.metric}`}><td>{value.ticker}</td><td>{value.metric}</td><td>{value.value == null ? "N/A" : `${value.value.toLocaleString()} ${value.unit ?? ""}`}</td><td>{value.freshness_days == null ? "—" : `${value.freshness_days}d`}</td><td>{value.evidence_ids.length} source IDs</td><td>{value.status}{value.reason ? ` · ${value.reason}` : ""}</td></tr>)}</tbody></table></div><div className="peer-layer-grid"><section><h4>Risk changes</h4>{analysis.risks.map((risk) => <p key={risk.ticker}><b>{risk.ticker}</b> · {risk.total} total · {risk.new} new · {risk.strengthened} stronger · {risk.weakened} weaker · {risk.evidence_ids.length} evidence IDs</p>)}</section><section><h4>Point-in-time expectations</h4>{analysis.expectations.map((point) => <p key={`${point.ticker}-${point.metric}-${point.fiscal_period}`}><b>{point.ticker}</b> · {point.metric} {point.value.toLocaleString()} {point.unit} · {point.fiscal_period} · {point.source}</p>)}{!analysis.expectations.length ? <p>No saved expectations.</p> : null}</section><section><h4>Valuation</h4>{analysis.valuations.map((value) => <p key={`${value.ticker}-${value.method}`}><b>{value.ticker}</b> · {value.method} · {value.value == null ? "N/A" : `${value.value.toFixed(2)}${value.unit === "x" ? "x" : "%"}`}</p>)}{!analysis.valuations.length ? <p>Supply explicit market and denominator inputs to compare valuation; no values are inferred.</p> : null}</section></div>{analysis.warnings.map((warning) => <p className="muted" key={warning}>{warning}</p>)}<p className="report-disclaimer">{analysis.disclaimer}</p></div> : null}
    </section>
  );
}
