"""Tests for the ``generate_company_report`` pipeline wrapper."""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.report_agent import DISCLAIMER, REPORT_SECTIONS
from src.pipelines.discover_opportunities import discover_opportunities
from src.pipelines.generate_report import generate_company_report
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


def _claims_and_evidence() -> tuple[list[Claim], list[Evidence]]:
    claims = [
        _claim("c-sc", "supply_chain", "Upstream supplier dynamics."),
        _claim("c-pol", "policy_exposure", "Policy beneficiary candidate."),
        _claim("c-sent", "sentiment", "Management tone is improving."),
        _claim("c-risk", "risk", "Risk factor disclosure."),
        _claim("c-geo", "geopolitical_exposure", "Region risk rising."),
    ]
    evidence = [ev for c in claims for ev in c.evidence]
    return claims, evidence


def test_report_contains_disclaimer() -> None:
    claims, evidence = _claims_and_evidence()
    hypotheses = discover_opportunities("ACME", claims, evidence)
    report = generate_company_report("ACME", hypotheses, claims, evidence)
    assert "Disclaimer" in report
    assert "investment advice" in report
    assert DISCLAIMER in report


def test_report_has_all_nine_sections() -> None:
    claims, evidence = _claims_and_evidence()
    hypotheses = discover_opportunities("ACME", claims, evidence)
    report = generate_company_report("ACME", hypotheses, claims, evidence)
    for section in REPORT_SECTIONS:
        # Each section must appear as a level-2 heading.
        assert f"## {section}" in report, f"missing section: {section}"


def test_each_hypothesis_appears_in_the_report() -> None:
    claims, evidence = _claims_and_evidence()
    hypotheses = discover_opportunities("ACME", claims, evidence)
    report = generate_company_report("ACME", hypotheses, claims, evidence)
    for hyp in hypotheses:
        assert hyp.title in report, f"hypothesis title missing: {hyp.title}"


def test_claim_without_evidence_is_not_asserted_in_body() -> None:
    """Claims lacking evidence must be excluded from body sections.

    The Sources section may still list them under the ``unsupported``
    banner, but the body sections (e.g. Risk and Counter-Evidence) must
    not assert them as if they had evidence.
    """
    supported = _claim("c-sc", "supply_chain", "Supply chain claim.")
    unsupported = Claim(
        claim_id="c-unsupported",
        claim_type="opportunity",
        statement="An unsupported claim that should not be asserted.",
        evidence=[],
        confidence=0.4,
    )
    claims = [supported, unsupported]
    evidence = [ev for c in claims for ev in c.evidence]
    hypotheses = [InvestmentHypothesis(
        hypothesis_id="hyp-x",
        title="A hypothesis",
        hypothesis_type="demand_acceleration",
        statement="A hypothesis statement.",
        companies=[],
        supporting_claims=[supported],
        evidence=supported.evidence,
        confidence=0.5,
    )]
    report = generate_company_report("ACME", hypotheses, claims, evidence)
    # The unsupported statement must not appear in the Opportunity
    # Hypotheses body (which only lists supported hypotheses). It may
    # appear in Sources.
    opportunity_section_start = report.index("## Opportunity Hypotheses")
    opportunity_section_end = report.index("## Risks and Counter-Evidence")
    body = report[opportunity_section_start:opportunity_section_end]
    assert "An unsupported claim" not in body


def test_report_cites_evidence_for_asserted_claims() -> None:
    claims, evidence = _claims_and_evidence()
    hypotheses = discover_opportunities("ACME", claims, evidence)
    report = generate_company_report("ACME", hypotheses, claims, evidence)
    # Every hypothesis body line must end with bracketed citation(s).
    import re

    body_start = report.index("## Opportunity Hypotheses")
    body_end = report.index("## Risks and Counter-Evidence")
    body = report[body_start:body_end]
    for line in body.splitlines():
        if line.startswith("### "):
            continue
        if not line.strip().startswith("-"):
            continue
        # Citation markers must be present.
        assert re.search(r"\[\d+\]", line), f"line missing citation: {line!r}"


def test_report_contains_disclaimer_text() -> None:
    claims, evidence = _claims_and_evidence()
    hypotheses = discover_opportunities("ACME", claims, evidence)
    report = generate_company_report("ACME", hypotheses, claims, evidence)
    # The disclaimer line is always appended as the final non-empty line.
    lines = [ln for ln in report.splitlines() if ln.strip()]
    assert "This report is for research only and is not investment advice." in lines[-1]


def test_report_dedupes_repeated_evidence() -> None:
    """A given evidence_id should appear at most once in the Key Evidence list."""
    claims, evidence = _claims_and_evidence()
    duplicate = evidence[0].model_copy(deep=True)
    evidence_with_dup = evidence + [duplicate]
    hypotheses = discover_opportunities("ACME", claims, evidence_with_dup)
    report = generate_company_report(
        "ACME", hypotheses, claims, evidence_with_dup
    )
    key_section_start = report.index("## Key Evidence")
    key_section_end = report.index("## Supply Chain Map")
    body = report[key_section_start:key_section_end]
    target_quote = duplicate.quote[:200]
    assert body.count(target_quote) == 1
