"""Tests for V21 AgentRunState models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.agents.state import AgentDecision, AgentRunState, AgentSubgoal


def test_agent_run_state_json_round_trip() -> None:
    state = AgentRunState(
        user_goal="Research Apple supply chain risk",
        workflow_kind="finrisk",
        subgoals=[
            AgentSubgoal(
                subgoal_id="sg-1",
                objective="Collect market evidence",
                tool_scope="finrisk_market",
                required_evidence_types=["web"],
            )
        ],
    )
    state.append_decision(
        AgentDecision(
            decision_type="call_tools",
            subgoal_id="sg-1",
            rationale="Need web evidence.",
            selected_tool_scope="finrisk_market",
        )
    )

    payload = state.model_dump_json()
    decoded = AgentRunState.model_validate_json(payload)

    assert decoded == state
    json.loads(payload)


def test_append_decision_merges_new_subgoals_once() -> None:
    state = AgentRunState(user_goal="x")
    subgoal = AgentSubgoal(subgoal_id="sg-fixed", objective="Search web")
    decision = AgentDecision(
        decision_type="plan",
        rationale="initial plan",
        next_subgoals=[subgoal, subgoal],
    )

    state.append_decision(decision)

    assert len(state.decisions) == 1
    assert [item.subgoal_id for item in state.subgoals] == ["sg-fixed"]


def test_next_pending_subgoal_respects_dependencies() -> None:
    first = AgentSubgoal(subgoal_id="sg-1", objective="First")
    second = AgentSubgoal(
        subgoal_id="sg-2",
        objective="Second",
        depends_on=["sg-1"],
    )
    state = AgentRunState(user_goal="x", subgoals=[first, second])

    assert state.next_pending_subgoal().subgoal_id == "sg-1"
    first.status = "completed"

    assert state.next_pending_subgoal().subgoal_id == "sg-2"


def test_stop_decision_requires_stop_reason() -> None:
    with pytest.raises(ValidationError):
        AgentDecision(decision_type="stop", rationale="done")


def test_non_stop_decision_rejects_stop_reason() -> None:
    with pytest.raises(ValidationError):
        AgentDecision(
            decision_type="plan",
            rationale="planning",
            stop_reason="enough_evidence",
        )
