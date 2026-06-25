"""Tests for the CriticAgent."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.agents.critic import CriticAgent
from src.agents.state import AgentState
from src.schemas.claims import Claim
from src.schemas.evidence import Evidence


def _evidence(eid: str = "ev1", quote: str = "Some quote.") -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_type="sec_filing",
        source_id="src",
        quote=quote,
        retrieved_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        confidence=0.9,
    )


def _claim(
    cid: str = "c1",
    evidence: list[Evidence] | None = None,
    confidence: float = 0.5,
) -> Claim:
    return Claim(
        claim_id=cid,
        claim_type="risk",
        statement="x",
        evidence=evidence if evidence is not None else [],
        confidence=confidence,
    )


@pytest.fixture
def critic() -> CriticAgent:
    return CriticAgent()


def test_critic_name(critic: CriticAgent) -> None:
    assert critic.name == "critic"


def test_critic_drops_claim_without_evidence(critic: CriticAgent) -> None:
    state = AgentState(
        goal="x",
        claims=[_claim("c1", evidence=[]), _claim("c2", evidence=[_evidence()])],
    )
    out = critic.run(state)
    assert [c.claim_id for c in out.claims] == ["c2"]
    assert any("c1" in n and "no evidence" in n for n in out.notes)


def test_critic_lowers_high_confidence_claim_with_too_little_evidence(
    critic: CriticAgent,
) -> None:
    claim = _claim("c1", evidence=[_evidence()], confidence=0.95)
    state = AgentState(goal="x", claims=[claim])
    out = critic.run(state)
    assert out.claims[0].confidence == critic.HIGH_CONFIDENCE_CAP
    assert any("lowered confidence" in n for n in out.notes)


def test_critic_keeps_high_confidence_with_two_evidence(
    critic: CriticAgent,
) -> None:
    claim = _claim(
        "c1",
        evidence=[_evidence("ev1"), _evidence("ev2", quote="other quote")],
        confidence=0.95,
    )
    state = AgentState(goal="x", claims=[claim])
    out = critic.run(state)
    assert out.claims[0].confidence == 0.95


def test_critic_keeps_low_confidence_with_single_evidence(
    critic: CriticAgent,
) -> None:
    claim = _claim("c1", evidence=[_evidence()], confidence=0.5)
    state = AgentState(goal="x", claims=[claim])
    out = critic.run(state)
    assert out.claims[0].confidence == 0.5


def test_evidence_rejects_empty_quote() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="ev1",
            source_type="sec_filing",
            source_id="src",
            quote="   ",
            retrieved_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            confidence=0.9,
        )


def test_critic_drops_empty_evidence(critic: CriticAgent) -> None:
    # Bypass the validator to simulate a stale or hand-built evidence list.
    ev = _evidence()
    bad_ev = ev.model_construct(
        **{**ev.model_dump(), "quote": ""},
    )
    state = AgentState(goal="x", evidence=[bad_ev, ev])  # type: ignore[list-item]
    out = critic.run(state)
    assert [e.evidence_id for e in out.evidence] == ["ev1"]
    assert any("empty quote" in n for n in out.notes)
