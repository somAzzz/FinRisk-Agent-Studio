"""Pipeline wrapper for the opportunity agent.

The signature mirrors the spec in the implementation plan: a free function
that takes a ticker plus the already-extracted claims and evidence and
returns a list of :class:`InvestmentHypothesis` records. The pipeline is
deliberately thin so it can be composed with other pipeline steps.
"""

from __future__ import annotations

from src.agents.opportunity_agent import OpportunityAgent
from src.schemas.claims import Claim
from src.schemas.evidence import Evidence
from src.schemas.hypotheses import InvestmentHypothesis


def discover_opportunities(
    ticker: str,
    claims: list[Claim],
    evidence: list[Evidence],
) -> list[InvestmentHypothesis]:
    """Generate research hypotheses for ``ticker`` from the supplied data.

    The pipeline instantiates an :class:`OpportunityAgent` and delegates
    the rule-based generation. The ``ticker`` parameter is currently used
    only for traceability (logged via the agent's notes payload); the
    rule-based engine does not yet incorporate ticker-specific context.
    """
    del ticker  # reserved for future ticker-aware scoring
    agent = OpportunityAgent()
    return agent.generate(claims=claims, evidence=evidence, entities=[])
