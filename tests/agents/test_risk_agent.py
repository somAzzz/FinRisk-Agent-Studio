"""Tests for the ``RiskAgent`` aggregator and categorizer."""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.risk_agent import (
    CATEGORY_KEYWORDS,
    RISK_CATEGORIES,
    RiskAgent,
    _categorize,
    _top_categories,
)
from src.agents.state import AgentState
from src.pipelines.analyze_risks import analyze_company_risks
from src.schemas.claims import Claim
from src.schemas.evidence import Evidence
from src.schemas.filings import FilingRecord


def _evidence(
    eid: str,
    quote: str,
    *,
    source_type: str = "sec_filing",
) -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_type=source_type,
        source_id="src",
        quote=quote,
        retrieved_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        confidence=0.8,
    )


def _risk_claim(statement: str, quote: str) -> Claim:
    return Claim(
        claim_id=f"c:{statement[:30]}",
        claim_type="risk",
        statement=statement,
        evidence=[_evidence(f"ev:{statement[:20]}", quote)],
        confidence=0.6,
    )


def test_risk_agent_name() -> None:
    assert RiskAgent().name == "risk"


def test_aggregates_risk_claims() -> None:
    state = AgentState(
        goal="x",
        ticker="ACME",
        evidence=[
            _evidence("e1", "Tariff exposure is significant."),
            _evidence("e2", "Customer concentration is a top risk."),
        ],
        claims=[
            _risk_claim("Tariff risk", "Tariff exposure is significant."),
            _risk_claim(
                "Customer concentration",
                "Customer concentration is a top risk.",
            ),
            Claim(
                claim_id="nonrisk",
                claim_type="sentiment",
                statement="Ignore me",
                evidence=[],
                confidence=0.5,
            ),
        ],
    )
    out = RiskAgent().run(state)
    summary_claims = [
        c
        for c in out.claims
        if c.claim_type == "risk" and c.claim_id.startswith("risk_category:")
    ]
    assert summary_claims, "expected per-category summary claims"
    # Both original risk claims still present.
    original_ids = {c.claim_id for c in out.claims if c.claim_id.startswith("c:")}
    assert "c:Tariff risk" in original_ids
    assert "c:Customer concentration" in original_ids


def test_categorization_by_keyword() -> None:
    claim = Claim(
        claim_id="c1",
        claim_type="risk",
        statement="Supply chain disruption",
        evidence=[
            _evidence(
                "e1",
                "Our supply chain faces a bottleneck due to a shortage of "
                "components.",
            )
        ],
        confidence=0.6,
    )
    categories = _categorize(claim)
    assert "supply_chain" in categories


def test_categorize_returns_all_matching_categories() -> None:
    claim = Claim(
        claim_id="c1",
        claim_type="risk",
        statement="Multiple risks",
        evidence=[
            _evidence(
                "e1",
                "Tariff exposure, antitrust litigation, and supply chain "
                "disruption all present risk.",
            )
        ],
        confidence=0.6,
    )
    categories = _categorize(claim)
    assert "policy" in categories
    assert "supply_chain" in categories
    assert "legal" in categories


def test_top_risk_categories_ordering() -> None:
    counts = {
        "macro": 1,
        "policy": 4,
        "geopolitical": 2,
        "supply_chain": 4,
        "customer_concentration": 0,
        "margin": 3,
        "legal": 0,
        "market": 0,
    }
    ordered = _top_categories(counts)
    # Counts of 4 come first, ordered alphabetically; then 3, then 2, then 1.
    assert ordered[0] in {"policy", "supply_chain"}
    assert ordered[1] in {"policy", "supply_chain"}
    assert ordered[0] != ordered[1]
    assert "margin" in ordered
    assert "geopolitical" in ordered
    assert "macro" in ordered
    # Categories with zero counts should not appear.
    assert "customer_concentration" not in ordered
    assert "legal" not in ordered
    assert "market" not in ordered


def test_top_categories_uses_all_categories() -> None:
    for cat in RISK_CATEGORIES:
        assert cat in CATEGORY_KEYWORDS


def test_pipeline_analyze_company_risks_returns_assessment() -> None:
    filing = FilingRecord(
        source="sec",
        cik="0001",
        ticker="ACME",
        company_name="Acme Corp",
        form_type="10-K",
        year=2026,
        sections={
            "section_1A": (
                "Tariff exposure from China and customer concentration "
                "are key risks. Supply chain disruption may pressure margins."
            ),
        },
    )
    assessment = analyze_company_risks(
        ticker="ACME",
        filings=[filing],
        transcripts=[],
        web_evidence=[],
    )
    assert 0.0 <= assessment.overall_risk_score <= 1.0
    assert assessment.risks, "expected seeded risk claims"
    assert all(c.claim_type == "risk" for c in assessment.risks)
    assert "policy" in assessment.top_risk_categories
    assert "supply_chain" in assessment.top_risk_categories


def test_pipeline_empty_inputs_returns_zero_score() -> None:
    assessment = analyze_company_risks(
        ticker="ACME",
        filings=[],
        transcripts=[],
        web_evidence=[],
    )
    assert assessment.overall_risk_score == 0.0
    assert assessment.top_risk_categories == []
    assert assessment.risks == []
