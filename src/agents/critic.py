"""Rule-based critic that cleans up claims and evidence."""

from __future__ import annotations

from src.agents.base import Agent
from src.agents.state import AgentState


class CriticAgent:
    """Apply conservative post-processing rules to ``state``."""

    name: str = "critic"

    HIGH_CONFIDENCE_THRESHOLD = 0.9
    HIGH_CONFIDENCE_CAP = 0.8
    MIN_EVIDENCE_FOR_HIGH_CONFIDENCE = 2

    def run(self, state: AgentState) -> AgentState:
        """Critique and clean ``state`` in place, returning the same object."""
        # Rule 1: drop claims with no evidence.
        kept_claims = []
        for claim in state.claims:
            if not claim.evidence:
                state.notes.append(
                    f"critic: dropped claim {claim.claim_id} with no evidence"
                )
                continue
            kept_claims.append(claim)
        state.claims = kept_claims

        # Rule 2: drop evidence with empty quotes.
        # The Evidence model already forbids empty quotes, but defensively
        # filter anything that slipped through (e.g. constructed via
        # model_construct in tests).
        kept_evidence = []
        for ev in state.evidence:
            if not ev.quote or not ev.quote.strip():
                state.notes.append(
                    f"critic: dropped evidence {ev.evidence_id} with empty quote"
                )
                continue
            kept_evidence.append(ev)
        state.evidence = kept_evidence

        # Rule 3: lower confidence for high-confidence claims with too little
        # supporting evidence.
        for claim in state.claims:
            if (
                claim.confidence > self.HIGH_CONFIDENCE_THRESHOLD
                and len(claim.evidence) < self.MIN_EVIDENCE_FOR_HIGH_CONFIDENCE
            ):
                claim.confidence = self.HIGH_CONFIDENCE_CAP
                state.notes.append(
                    "critic: lowered confidence to "
                    f"{self.HIGH_CONFIDENCE_CAP} for claim {claim.claim_id} "
                    "with insufficient evidence"
                )

        return state
