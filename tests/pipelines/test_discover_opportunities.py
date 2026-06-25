"""Tests for the ``discover_opportunities`` pipeline wrapper."""

from __future__ import annotations

from datetime import datetime, timezone

from src.pipelines.discover_opportunities import discover_opportunities
from src.schemas.claims import Claim
from src.schemas.evidence import Evidence
from src.schemas.hypotheses import InvestmentHypothesis


def _evidence(eid: str, quote: str = "quote") -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_type="sec_filing",
        source_id=f"src-{eid}",
        quote=quote,
        retrieved_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        confidence=0.8,
    )


def _claim(claim_id: str, claim_type: str, statement: str) -> Claim:
    return Claim(
        claim_id=claim_id,
        claim_type=claim_type,  # type: ignore[arg-type]
        statement=statement,
        evidence=[_evidence(f"ev-{claim_id}", statement)],
        confidence=0.6,
    )


def test_pipeline_returns_list_of_investment_hypothesis() -> None:
    claims = [
        _claim("c-sc", "supply_chain", "Supply chain claim."),
        _claim("c-pol", "policy_exposure", "Policy exposure claim."),
        _claim("c-sent", "sentiment", "Sentiment claim."),
        _claim("c-risk", "risk", "Risk claim."),
    ]
    evidence = [ev for c in claims for ev in c.evidence]
    result = discover_opportunities("ACME", claims, evidence)

    assert isinstance(result, list)
    assert result
    for hyp in result:
        assert isinstance(hyp, InvestmentHypothesis)
        assert hyp.evidence
        assert hyp.not_investment_advice is True


def test_pipeline_meets_three_hypothesis_minimum() -> None:
    claims = [
        _claim("c-sc", "supply_chain", "Supply chain claim."),
        _claim("c-pol", "policy_exposure", "Policy exposure claim."),
        _claim("c-sent", "sentiment", "Sentiment claim."),
        _claim("c-risk", "risk", "Risk claim."),
    ]
    evidence = [ev for c in claims for ev in c.evidence]
    result = discover_opportunities("ACME", claims, evidence)
    assert 3 <= len(result) <= 5


def test_ticker_does_not_affect_output_for_now() -> None:
    """The current pipeline ignores the ticker but must not error out.

    This documents the contract: passing any ticker should not raise.
    """
    claims = [
        _claim("c-sc", "supply_chain", "Supply chain claim."),
        _claim("c-pol", "policy_exposure", "Policy exposure claim."),
        _claim("c-sent", "sentiment", "Sentiment claim."),
        _claim("c-risk", "risk", "Risk claim."),
    ]
    evidence = [ev for c in claims for ev in c.evidence]
    a = discover_opportunities("AAA", claims, evidence)
    b = discover_opportunities("ZZZ", claims, evidence)
    assert len(a) == len(b)
