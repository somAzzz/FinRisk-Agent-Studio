// Placeholder shape for v16 claims; the matrix is best-effort
// because the v15 API doesn't yet expose claims. The component
// is here to anchor the v16 frontend contract.
export interface ClaimRow {
  claim_id: string;
  claim_type: "evidence" | "inference" | "hypothesis";
  text: string;
  supporting_evidence_ids: string[];
  grounding: "grounded" | "needs_review" | "unsupported" | "unknown";
  status: "pass" | "warning" | "fail" | "needs_review";
  recommendation: string | null;
}

interface Props {
  claims: ClaimRow[];
}

export function ClaimEvidenceMatrix({ claims }: Props) {
  if (!claims.length) {
    return (
      <div className="section empty-state" data-testid="claim-matrix-empty">
        Claim-Evidence matrix will appear here once the workflow
        surfaces v16 claims.
      </div>
    );
  }
  return (
    <div className="section" data-testid="claim-evidence-matrix">
      <h2>Claim-Evidence Matrix</h2>
      <table
        style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}
      >
        <thead>
          <tr>
            <th style={th}>Claim</th>
            <th style={th}>Type</th>
            <th style={th}>Evidence</th>
            <th style={th}>Grounding</th>
            <th style={th}>Status</th>
            <th style={th}>Recommendation</th>
          </tr>
        </thead>
        <tbody>
          {claims.map((c) => (
            <tr key={c.claim_id} data-testid={`claim-${c.claim_id}`}>
              <td style={td}>{c.text}</td>
              <td style={td}>{c.claim_type}</td>
              <td style={td} className="mono">
                {c.supporting_evidence_ids.join(", ") || "—"}
              </td>
              <td style={td}>{c.grounding}</td>
              <td style={td}>{c.status}</td>
              <td style={td}>{c.recommendation ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const th: React.CSSProperties = {
  border: "1px solid #e2e8f0",
  padding: "6px 8px",
  textAlign: "left",
  background: "#f8fafc",
};

const td: React.CSSProperties = {
  border: "1px solid #e2e8f0",
  padding: "6px 8px",
  verticalAlign: "top",
};
