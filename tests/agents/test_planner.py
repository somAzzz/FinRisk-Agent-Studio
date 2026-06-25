"""Tests for the rule-based PlannerAgent."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.agents.planner import AgentPlan, PlanStep, PlannerAgent
from src.agents.state import AgentState


def _evidence(source_type: str = "sec_filing", eid: str = "ev1") -> dict[str, object]:
    return {
        "evidence_id": eid,
        "source_type": source_type,
        "source_id": "src",
        "quote": "Some quote text.",
        "retrieved_at": datetime(2026, 6, 20, tzinfo=timezone.utc),
        "confidence": 0.9,
    }


@pytest.fixture
def planner() -> PlannerAgent:
    return PlannerAgent()


def test_planner_name(planner: PlannerAgent) -> None:
    assert planner.name == "planner"


def test_planner_returns_agent_plan(planner: PlannerAgent) -> None:
    state = AgentState(goal="x", ticker="AAPL")
    plan = planner.plan(state)
    assert isinstance(plan, AgentPlan)
    assert plan.steps  # at least discover_opportunity + finish


def test_planner_fetches_filing_when_ticker_without_evidence(
    planner: PlannerAgent,
) -> None:
    state = AgentState(goal="understand AAPL", ticker="AAPL")
    plan = planner.plan(state)
    actions = [step.action for step in plan.steps]
    assert "fetch_filing" in actions
    fetch_step = next(s for s in plan.steps if s.action == "fetch_filing")
    assert fetch_step.inputs == {"ticker": "AAPL"}
    assert plan.needs_more_info is True


def test_planner_extracts_entities_when_filing_present(
    planner: PlannerAgent,
) -> None:
    state = AgentState(
        goal="understand AAPL",
        ticker="AAPL",
        evidence=[_evidence(source_type="sec_filing")],  # type: ignore[list-item]
    )
    plan = planner.plan(state)
    actions = [step.action for step in plan.steps]
    assert "extract_entities" in actions
    assert "fetch_filing" not in actions


def test_planner_chain_progresses(planner: PlannerAgent) -> None:
    """As state grows, planner should advance to later steps."""
    state = AgentState(goal="understand AAPL", ticker="AAPL")

    # No evidence -> fetch_filing.
    plan1 = planner.plan(state)
    assert plan1.steps[0].action == "fetch_filing"

    # Add filing evidence -> next is extract_entities.
    state.evidence = [_evidence(source_type="sec_filing")]  # type: ignore[assignment]
    plan2 = planner.plan(state)
    assert plan2.steps[0].action == "extract_entities"


def test_planner_plan_is_finite_and_ends_with_discover_then_finish(
    planner: PlannerAgent,
) -> None:
    state = AgentState(goal="analyze NVDA earnings", ticker="NVDA")
    plan = planner.plan(state)
    assert plan.steps[-1].action == "finish"
    assert "discover_opportunity" in [s.action for s in plan.steps]
    # discover_opportunity should come immediately before finish.
    assert plan.steps[-2].action == "discover_opportunity"


def test_planner_run_records_note(planner: PlannerAgent) -> None:
    state = AgentState(goal="x")
    out = planner.run(state)
    assert any(note.startswith("planner:") for note in out.notes)


def test_planner_no_evidence_no_ticker_does_web_search(
    planner: PlannerAgent,
) -> None:
    state = AgentState(goal="explore healthcare trends")
    plan = planner.plan(state)
    actions = [step.action for step in plan.steps]
    assert "web_search" in actions


def test_plan_step_extra_forbid() -> None:
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError):
        PlanStep(
            step_id="s1",
            action="fetch_filing",
            reason="r",
            inputs={},
            extra="nope",  # type: ignore[call-arg]
        )
