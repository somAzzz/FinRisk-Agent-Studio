"""Pipeline wrapper for the report agent.

Produces a Markdown company research brief from the hypotheses, claims,
and evidence produced by upstream steps.
"""

from __future__ import annotations

from src.agents.report_agent import ReportAgent
from src.schemas.claims import Claim
from src.schemas.evidence import Evidence
from src.schemas.hypotheses import InvestmentHypothesis


def generate_company_report(
    ticker: str,
    hypotheses: list[InvestmentHypothesis],
    claims: list[Claim],
    evidence: list[Evidence],
) -> str:
    """Return a Markdown company research brief for ``ticker``."""
    agent = ReportAgent()
    return agent.generate(
        ticker=ticker,
        hypotheses=hypotheses,
        claims=claims,
        evidence=evidence,
    )
