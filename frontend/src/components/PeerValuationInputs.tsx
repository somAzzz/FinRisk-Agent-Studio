import type {
  MultipleValuationMethod,
  MultipleValuationRequest,
} from "../types";

export type Assumption = {
  id: string;
  ticker: string;
  method: MultipleValuationMethod;
  price: string;
  shares: string;
  denominator: string;
  debt: string;
  period: string;
  evidence: string;
};
const names = {
  pe: "Earnings",
  ev_ebitda: "EBITDA",
  fcf_yield: "Free cash flow",
};
export function valuationsFrom(rows: Assumption[]): MultipleValuationRequest[] {
  const number = (value: string, label: string, positive = false) => {
    const result = Number(value);
    if (!value.trim() || !Number.isFinite(result) || (positive && result <= 0))
      throw new Error("Enter a valid " + label + ".");
    return result;
  };
  return rows.map((r) => {
    if (!r.period.trim()) throw new Error("Specify the valuation period.");
    return {
      ticker: r.ticker,
      method: r.method,
      period: r.period.trim(),
      share_price: number(r.price, "share price", true),
      diluted_shares: number(r.shares, "diluted share count", true),
      net_debt: r.method === "ev_ebitda" ? number(r.debt, "net debt") : 0,
      [{ pe: "earnings", ev_ebitda: "ebitda", fcf_yield: "free_cash_flow" }[
        r.method
      ]]: number(r.denominator, names[r.method]),
      evidence_ids: r.evidence
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
  });
}
export function PeerValuationInputs({
  members,
  rows,
  onChange,
}: {
  members: string[];
  rows: Assumption[];
  onChange: (rows: Assumption[]) => void;
}) {
  return (
    <details className="cycle-details">
      <summary>Valuation assumptions (optional)</summary>
      <p>
        Use matching periods, currencies and units for each peer. Without
        inputs, valuation stays unavailable.
      </p>
      {rows.map((r) => {
        const change = (key: keyof Assumption, value: string) =>
          onChange(
            rows.map((x) => (x.id === r.id ? { ...x, [key]: value } : x)),
          );
        return (
          <fieldset key={r.id} className="peer-analysis-controls">
            <legend>{r.ticker} valuation</legend>
            <label>
              Company
              <select
                value={r.ticker}
                onChange={(e) => change("ticker", e.target.value)}
              >
                {members.map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </select>
            </label>
            <label>
              Method
              <select
                value={r.method}
                onChange={(e) =>
                  onChange(
                    rows.map((x) =>
                      x.id === r.id
                        ? {
                            ...x,
                            method: e.target.value as MultipleValuationMethod,
                            denominator: "",
                            debt: "",
                          }
                        : x,
                    ),
                  )
                }
              >
                <option value="pe">P/E</option>
                <option value="ev_ebitda">EV/EBITDA</option>
                <option value="fcf_yield">FCF yield</option>
              </select>
            </label>
            {(
              [
                ["price", "Share price"],
                ["shares", "Diluted shares"],
                ["denominator", names[r.method]],
                ...(r.method === "ev_ebitda" ? [["debt", "Net debt"]] : []),
                ["period", "Period"],
                ["evidence", "Evidence IDs (optional)"],
              ] as [keyof Assumption, string][]
            ).map(([k, label]) => (
              <label key={k}>
                {label}
                <input
                  type={k === "period" || k === "evidence" ? "text" : "number"}
                  step="any"
                  value={r[k]}
                  onChange={(e) => change(k, e.target.value)}
                />
              </label>
            ))}
            <button
              type="button"
              className="ghost"
              onClick={() => onChange(rows.filter((x) => x.id !== r.id))}
            >
              Remove assumption
            </button>
          </fieldset>
        );
      })}
      <button
        className="ghost"
        type="button"
        onClick={() =>
          onChange([
            ...rows,
            {
              id: crypto.randomUUID(),
              ticker: members[0],
              method: "pe",
              price: "",
              shares: "",
              denominator: "",
              debt: "",
              period: "",
              evidence: "",
            },
          ])
        }
      >
        Add valuation assumption
      </button>
    </details>
  );
}
