"""Step 4: normalize filing + market evidence into ``NormalizedEvidence``."""

from __future__ import annotations

from src.workflows.state import (
    FinRiskWorkflowState,
    NormalizedEvidence,
    utcnow,
)
from src.workflows.steps._base import WorkflowStep


class EvidenceNormalizerStep(WorkflowStep):
    """Convert raw ``filing_risks`` + ``market_evidence`` into ``NormalizedEvidence``.

    The step enforces:
    - one ``NormalizedEvidence`` row per filing risk (the evidence_quote is
      the canonical text);
    - one row per ``MarketEvidence`` whose ``supports_risk`` or
      ``contradicts_risk`` flag is true;
    - deduplication by ``source_url`` (market) or ``evidence_id`` (filing).
    """

    name = "evidence_normalizer"

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        company_name = (
            state.company.company_name if state.company else state.request.ticker
        )

        normalized: list[NormalizedEvidence] = []
        seen_keys: set[str] = set()

        for risk in state.filing_risks:
            key = f"filing:{risk.risk_id}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            normalized.append(
                NormalizedEvidence(
                    evidence_id=f"ne-{risk.risk_id}",
                    source_type="filing",
                    source_name=f"{company_name} {risk.filing_section or '10-K'}",
                    source_url=None,
                    quote=risk.evidence_quote,
                    summary=risk.risk_factor,
                    related_risk_ids=[risk.risk_id],
                    credibility_score=0.9,
                    collected_at=utcnow(),
                )
            )

        for ev in state.market_evidence:
            url_key = ev.source_url.strip().lower()
            key = f"market:{url_key}"
            if not ev.supports_risk and not ev.contradicts_risk:
                # Skip market evidence that is neither supportive nor
                # contradicting; it would be noise in the final report.
                continue
            if key in seen_keys:
                continue
            seen_keys.add(key)
            # Tag the market evidence as supporting or contradicting so
            # downstream report sections can render counter-evidence.
            summary_suffix = (
                "supports the risk"
                if ev.supports_risk
                else "contradicts the risk"
            )
            normalized.append(
                NormalizedEvidence(
                    evidence_id=f"ne-{ev.evidence_id}",
                    source_type="web",
                    source_name=ev.source_title or ev.source_type,
                    source_url=ev.source_url,
                    quote=ev.evidence_summary,
                    summary=f"{ev.claim} ({summary_suffix})",
                    related_risk_ids=[ev.risk_id] if ev.risk_id else [],
                    credibility_score=ev.confidence,
                    collected_at=ev.timestamp,
                )
            )

        state.normalized_evidence = normalized
        return state


__all__ = ["EvidenceNormalizerStep"]