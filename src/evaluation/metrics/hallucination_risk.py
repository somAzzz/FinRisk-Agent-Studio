"""Hallucination risk metric.

The v15 report evaluator computed a hallucination score from
the ratio of unsupported top risks. The v16 metric refines the
calculation by also counting claim-level mismatches when claims
are present in the state.
"""

from __future__ import annotations

from src.schemas.finrisk import FinRiskWorkflowState


def hallucination_risk_score(state: FinRiskWorkflowState) -> float:
    """Return a hallucination risk score in ``[0, 1]``.

    The score is the larger of:

    - fraction of top risks without any evidence row, and
    - fraction of state claims whose ``supporting_evidence_ids``
      point at evidence that does not exist in
      ``state.normalized_evidence``.

    A score of ``0.0`` means everything is grounded; ``1.0`` means
    the report is fully unsupported.
    """
    if state.report is None and not state.claims:
        return 0.0

    risk_score = 0.0
    if state.report is not None and state.report.top_risks:
        valid = {ev.evidence_id for ev in state.normalized_evidence}
        risk_to_ev: dict[str, set[str]] = {r.risk_id: set() for r in state.report.top_risks}
        for ev in state.report.evidence_table:
            for rid in ev.related_risk_ids or []:
                if rid in risk_to_ev and ev.evidence_id in valid:
                    risk_to_ev[rid].add(ev.evidence_id)
        uncovered = sum(1 for ids in risk_to_ev.values() if not ids)
        risk_score = uncovered / max(1, len(risk_to_ev))

    claim_score = 0.0
    if state.claims:
        valid = {ev.evidence_id for ev in state.normalized_evidence}
        bad = sum(
            1
            for claim in state.claims
            if not claim.supporting_evidence_ids
            or any(eid not in valid for eid in claim.supporting_evidence_ids)
        )
        claim_score = bad / max(1, len(state.claims))

    return round(min(1.0, max(risk_score, claim_score)), 4)


__all__ = ["hallucination_risk_score"]
