"""Tests for the V21 structured AgentPlanner."""

from __future__ import annotations

import json

from src.agents.planner import AgentPlanner
from src.agents.state import AgentRunState


def test_agent_planner_initializes_finrisk_subgoals() -> None:
    planner = AgentPlanner()

    state = planner.initialize(
        user_goal="Assess Apple supply chain risk",
        workflow_kind="finrisk",
    )

    assert state.workflow_kind == "finrisk"
    assert state.decisions[0].decision_type == "plan"
    assert len(state.subgoals) >= 3
    assert {subgoal.tool_scope for subgoal in state.subgoals} >= {
        "company_research",
        "finrisk_market",
    }


def test_agent_planner_calls_next_pending_subgoal() -> None:
    planner = AgentPlanner()
    state = planner.initialize(user_goal="Research NVIDIA", workflow_kind="generic_research")

    decision = planner.decide(state)

    assert decision.decision_type == "call_tools"
    assert decision.subgoal_id == state.subgoals[0].subgoal_id
    assert decision.selected_tool_scope == "company_research"


def test_agent_planner_uses_structured_planner_output() -> None:
    def structured(_state: AgentRunState) -> dict:
        return {
            "decision_type": "call_tools",
            "rationale": "Use supply chain tools.",
            "selected_tool_scope": "supply_chain",
            "selected_tools": ["web_search"],
            "confidence": 0.8,
        }

    planner = AgentPlanner(llm_planner=structured)
    decision = planner.decide(AgentRunState(user_goal="OpenAI suppliers"))

    assert decision.decision_type == "call_tools"
    assert decision.selected_tool_scope == "supply_chain"
    assert decision.selected_tools == ["web_search"]


def test_agent_planner_accepts_json_planner_output() -> None:
    def structured(_state: AgentRunState) -> str:
        return json.dumps(
            {
                "decision_type": "stop",
                "rationale": "Enough evidence.",
                "stop_reason": "enough_evidence",
                "confidence": 0.9,
            }
        )

    decision = AgentPlanner(llm_planner=structured).decide(
        AgentRunState(user_goal="x")
    )

    assert decision.decision_type == "stop"
    assert decision.rationale == "Enough evidence."
    assert decision.stop_reason == "enough_evidence"
    assert decision.confidence == 0.9


def test_agent_planner_bad_json_falls_back_to_deterministic_plan() -> None:
    planner = AgentPlanner(llm_planner=lambda _state: "{bad json")
    state = AgentRunState(user_goal="Research Apple", workflow_kind="finrisk")

    decision = planner.decide(state)

    assert decision.decision_type == "plan"
    assert decision.next_subgoals
    assert state.fallback_events


def test_agent_planner_rejects_unknown_tool_scope_and_falls_back() -> None:
    def structured(_state: AgentRunState) -> dict:
        return {
            "decision_type": "call_tools",
            "rationale": "Try unsafe scope.",
            "selected_tool_scope": "graph_write",
        }

    planner = AgentPlanner(llm_planner=structured)
    state = AgentRunState(user_goal="x")

    decision = planner.decide(state)

    assert decision.decision_type == "plan"
    assert "unknown tool scope" in state.fallback_events[0]
