"""Tests for the keyword-based ``PolicyGeoAgent``."""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.policy_geo_agent import PolicyGeoAgent
from src.agents.state import AgentState
from src.schemas.analysis import GeopoliticalExposure, PolicyExposure
from src.schemas.claims import Claim
from src.schemas.evidence import Evidence


def _evidence(
    eid: str,
    quote: str,
    *,
    source_type: str = "sec_filing",
    section: str = "section_1A",
) -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_type=source_type,
        source_id="src",
        quote=quote,
        section=section,
        retrieved_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        confidence=0.8,
    )


def test_policy_geo_agent_name() -> None:
    assert PolicyGeoAgent().name == "policy_geo"


def test_detects_ira_keyword() -> None:
    state = AgentState(
        goal="x",
        ticker="ACME",
        evidence=[
            _evidence(
                "ira1",
                "We benefit from the Inflation Reduction Act via clean "
                "energy credits and Section 45X incentives.",
            ),
        ],
    )
    out = PolicyGeoAgent().run(state)
    policy_claims = [c for c in out.claims if c.claim_type == "policy_exposure"]
    assert policy_claims, "expected at least one policy_exposure claim"
    statements = " ".join(c.statement for c in policy_claims)
    assert "IRA" in statements


def test_produces_policy_and_geopolitical_exposures() -> None:
    state = AgentState(
        goal="x",
        ticker="ACME",
        evidence=[
            _evidence(
                "ira1",
                "We are a beneficiary of the Inflation Reduction Act with "
                "solar tax credits.",
            ),
            _evidence(
                "chips1",
                "The CHIPS Act supports our semiconductor fab investment.",
            ),
            _evidence(
                "tariff1",
                "New tariffs on imports from China may pressure margins.",
            ),
            _evidence(
                "sanction1",
                "Sanctions on Russia and ongoing conflict in Ukraine affect "
                "supply chains.",
            ),
        ],
    )
    out = PolicyGeoAgent().run(state)
    policy_claims = [c for c in out.claims if c.claim_type == "policy_exposure"]
    geo_claims = [c for c in out.claims if c.claim_type == "geopolitical_exposure"]
    assert policy_claims, "expected policy_exposure claims"
    assert geo_claims, "expected geopolitical_exposure claims"

    # All claims must carry evidence.
    for claim in policy_claims + geo_claims:
        assert claim.evidence, f"claim {claim.claim_id} has no evidence"


def test_risk_score_within_unit_interval() -> None:
    state = AgentState(
        goal="x",
        ticker="ACME",
        evidence=[
            _evidence(
                "g1",
                "Trade war tariffs and sanctions on China create significant "
                "risk for our supply chain.",
            ),
            _evidence(
                "g2",
                "Red Sea shipping disruption is causing logistics delays.",
            ),
        ],
    )
    out = PolicyGeoAgent().run(state)
    geo_claims = [c for c in out.claims if c.claim_type == "geopolitical_exposure"]
    assert geo_claims
    for claim in geo_claims:
        # The risk_score is encoded in the statement, but we also re-derive it
        # by parsing the statement and clamping to [0, 1].
        assert "risk_score=" in claim.statement
        score_str = claim.statement.rsplit("risk_score=", 1)[-1].rstrip(").")
        score = float(score_str)
        assert 0.0 <= score <= 1.0


def test_policy_exposure_evidence_anchored() -> None:
    state = AgentState(
        goal="x",
        ticker="ACME",
        evidence=[
            _evidence("p1", "We benefit from the CHIPS Act incentives."),
        ],
    )
    out = PolicyGeoAgent().run(state)
    claims = [c for c in out.claims if c.claim_type == "policy_exposure"]
    assert claims
    for claim in claims:
        assert isinstance(claim, Claim)
        assert claim.evidence
        for ev in claim.evidence:
            assert ev.quote
            assert ev.source_type in {"sec_filing", "transcript", "web", "browser"}


def test_analyst_only_evidence_excluded() -> None:
    state = AgentState(
        goal="x",
        ticker="ACME",
        evidence=[
            Evidence(
                evidence_id="a1",
                source_type="transcript",
                source_id="src",
                quote="Should we worry about new tariffs on China?",
                section="qa",
                retrieved_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
                confidence=0.8,
                metadata={"role": "analyst"},
            ),
        ],
    )
    out = PolicyGeoAgent().run(state)
    # No management evidence to anchor on -> no policy/geo claims produced.
    assert not [c for c in out.claims if c.claim_type in {
        "policy_exposure",
        "geopolitical_exposure",
    }]
