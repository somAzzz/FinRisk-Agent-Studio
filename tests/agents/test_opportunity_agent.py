"""Tests for the ``OpportunityAgent`` rule-based hypothesis generator."""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.opportunity_agent import (
    ALLOWED_HYPOTHESIS_TYPES,
    OpportunityAgent,
    is_opportunity_agent,
)
from src.agents.state import AgentState
from src.schemas.claims import Claim, ClaimType
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence, SourceType


def _evidence(eid: str, quote: str = "n/a") -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_type="sec_filing",
        source_id=f"src-{eid}",
        quote=quote,
        retrieved_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        confidence=0.8,
    )


def _entity(name: str) -> Entity:
    return Entity(
        entity_id=f"ent-{name}",
        name=name,
        entity_type="company",
        normalized_name=name.lower(),
        confidence=0.9,
    )


def _claim(
    claim_id: str,
    claim_type: ClaimType,
    statement: str,
    *,
    entities: list[Entity] | None = None,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        claim_type=claim_type,
        statement=statement,
        entities=entities or [_entity("ACME")],
        evidence=[_evidence(f"ev-{claim_id}", statement)],
        confidence=0.7,
    )


def _state(*claims: Claim) -> AgentState:
    evidence = [ev for c in claims for ev in c.evidence]
    return AgentState(
        goal="find opportunities",
        ticker="ACME",
        claims=list(claims),
        evidence=evidence,
    )


def test_agent_name() -> None:
    agent = OpportunityAgent()
    assert agent.name == "opportunity"
    assert is_opportunity_agent(agent)


def test_produces_three_to_five_hypotheses() -> None:
    claims = [
        _claim("c-sc", "supply_chain", "Upstream supplier dynamics."),
        _claim("c-pol", "policy_exposure", "Policy beneficiary candidate."),
        _claim("c-sent", "sentiment", "Management tone is improving."),
        _claim("c-risk", "risk", "Disclosed risk factor."),
        _claim("c-geo", "geopolitical_exposure", "Region risk rising."),
    ]
    state = _state(*claims)
    new_state = OpportunityAgent().run(state)

    # Hypotheses are stored serialised on state.notes.
    payload = [n for n in new_state.notes if n.startswith("opportunity:hypotheses=")]
    assert payload, "expected hypotheses to be recorded on state.notes"
    assert any(
        n.startswith("opportunity:hypotheses_count=") for n in new_state.notes
    )

    # The agent must honour the 3-5 contract.
    count_line = [
        n
        for n in new_state.notes
        if n.startswith("opportunity:hypotheses_count=")
    ][0]
    count = int(count_line.split("=")[1])
    assert 3 <= count <= 5


def test_each_hypothesis_has_at_least_one_evidence() -> None:
    claims = [
        _claim("c-sc", "supply_chain", "Upstream supplier dynamics."),
        _claim("c-pol", "policy_exposure", "Policy beneficiary candidate."),
        _claim("c-sent", "sentiment", "Management tone is improving."),
        _claim("c-risk", "risk", "Disclosed risk factor."),
    ]
    state = _state(*claims)
    new_state = OpportunityAgent().run(state)
    raw = [n for n in new_state.notes if n.startswith("opportunity:hypotheses=")][0]
    import json

    serialised = json.loads(raw.split("=", 1)[1])
    for hyp in serialised:
        assert hyp["evidence"], f"hypothesis {hyp['hypothesis_id']} has no evidence"


def test_not_investment_advice_true_on_all_hypotheses() -> None:
    claims = [
        _claim("c-sc", "supply_chain", "Supply chain claim."),
        _claim("c-pol", "policy_exposure", "Policy exposure claim."),
        _claim("c-sent", "sentiment", "Sentiment claim."),
        _claim("c-risk", "risk", "Risk claim."),
    ]
    state = _state(*claims)
    new_state = OpportunityAgent().run(state)
    raw = [n for n in new_state.notes if n.startswith("opportunity:hypotheses=")][0]
    import json

    serialised = json.loads(raw.split("=", 1)[1])
    assert serialised, "expected at least one hypothesis"
    for hyp in serialised:
        assert hyp["not_investment_advice"] is True


def test_hypothesis_types_are_from_allowed_set() -> None:
    claims = [
        _claim("c-sc", "supply_chain", "Supply chain claim."),
        _claim("c-pol", "policy_exposure", "Policy exposure claim."),
        _claim("c-sent", "sentiment", "Sentiment claim."),
        _claim("c-risk", "risk", "Risk claim."),
        _claim("c-geo", "geopolitical_exposure", "Geopolitical claim."),
    ]
    state = _state(*claims)
    new_state = OpportunityAgent().run(state)
    raw = [n for n in new_state.notes if n.startswith("opportunity:hypotheses=")][0]
    import json

    serialised = json.loads(raw.split("=", 1)[1])
    assert serialised
    for hyp in serialised:
        assert hyp["hypothesis_type"] in ALLOWED_HYPOTHESIS_TYPES


def test_generate_returns_pydantic_instances() -> None:
    claims = [
        _claim("c-sc", "supply_chain", "Supply chain claim."),
        _claim("c-pol", "policy_exposure", "Policy exposure claim."),
        _claim("c-sent", "sentiment", "Sentiment claim."),
        _claim("c-risk", "risk", "Risk claim."),
    ]
    agent = OpportunityAgent()
    result = agent.generate(
        claims=claims,
        evidence=[ev for c in claims for ev in c.evidence],
        entities=[],
    )
    assert 3 <= len(result) <= 5
    for hyp in result:
        assert hyp.not_investment_advice is True
        assert hyp.evidence
        assert hyp.hypothesis_type in ALLOWED_HYPOTHESIS_TYPES
        # Confidence must respect the schema bounds.
        assert 0.0 <= hyp.confidence <= 1.0


def test_dedupe_drops_repeated_hypotheses() -> None:
    """Two hypotheses with the same (type, title, statement) collapse to one."""
    claim = _claim("c-1", "supply_chain", "Supplier concentration risk.")
    evidence = [_evidence("e-1", "Supplier concentration risk text")]
    # Pass the same claim list twice to force duplicates through the
    # builder padding loop.
    result = OpportunityAgent().generate(
        [claim, claim, claim], evidence, entities=[]
    )
    keys = {(h.hypothesis_type, h.title, h.statement) for h in result}
    assert len(keys) == len(result)


def test_priority_orders_supply_chain_before_demand() -> None:
    """Output is sorted so supply_chain_opportunity outranks demand_acceleration."""
    claim = _claim("c-1", "supply_chain", "Supplier concentration risk.")
    evidence = [_evidence("e-1", "Supplier concentration risk text")]
    result = OpportunityAgent().generate(
        [claim], evidence, entities=[]
    )
    if len(result) >= 2:
        priority = {
            "supply_chain_opportunity": 0,
            "demand_acceleration": 5,
        }
        indices = [priority.get(h.hypothesis_type, 99) for h in result]
        assert indices == sorted(indices)
