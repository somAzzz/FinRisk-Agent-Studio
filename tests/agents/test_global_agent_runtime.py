"""Tests for the V21 GlobalAgentRuntime."""

from __future__ import annotations

import json

from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.llm_runtime import LLMToolRunResult
from src.agents.state import AgentBudget, AgentSubgoal
from src.schemas.tool_trace import ToolExecutionEvent
from src.workflows.state import utcnow


class FakeRuntime:
    def __init__(self, events: list[ToolExecutionEvent]) -> None:
        self.events = events

    def run(self, goal: str) -> LLMToolRunResult:
        return LLMToolRunResult(
            goal=goal,
            final_answer="done",
            tool_events=self.events,
        )


def _web_event(
    snippet: str = "Apple supplier pressure affects supply chain planning.",
) -> ToolExecutionEvent:
    payload = {
        "tool": "web_search",
        "status": "success",
        "data": {
            "query": "Apple supplier pressure",
            "results": [
                {
                    "title": "Apple supplier pressure",
                    "url": "https://example.com/apple",
                    "snippet": snippet,
                    "rank": 1,
                }
            ],
        },
    }
    return ToolExecutionEvent(
        event_id="event-1",
        round_id="round-0",
        tool_call_id="call-1",
        tool_name="web_search",
        arguments={"query": "Apple supplier pressure"},
        status="success",
        result_summary=json.dumps(payload),
        latency_ms=1,
        result_chars=100,
        created_at=utcnow(),
    )


def test_global_agent_runtime_executes_subgoals_and_collects_candidates() -> None:
    runtime = GlobalAgentRuntime(
        subgoal_runtime_factory=lambda _scope, _subgoal: FakeRuntime([_web_event()])
    )

    state = runtime.run(
        "Assess Apple supply chain risk",
        workflow_kind="finrisk",
    )

    assert state.status == "completed"
    assert state.subgoals
    assert state.tool_traces
    assert state.evidence_candidates
    assert state.accepted_evidence_ids
    assert any(decision.decision_type == "stop" for decision in state.decisions)


def test_global_agent_runtime_stops_when_subgoal_budget_exhausted() -> None:
    runtime = GlobalAgentRuntime(
        subgoal_runtime_factory=lambda _scope, subgoal: FakeRuntime(
            [_web_event(snippet=subgoal.objective)]
        )
    )
    state = runtime.run(
        "x",
        workflow_kind="finrisk",
        budget=AgentBudget(max_subgoals=1),
    )

    assert state.decisions[-1].decision_type == "stop"
    assert state.decisions[-1].stop_reason == "budget_exhausted"


def test_global_agent_runtime_failed_subgoal_records_fallback() -> None:
    class BrokenRuntime:
        def run(self, _goal: str) -> LLMToolRunResult:
            raise RuntimeError("model offline")

    runtime = GlobalAgentRuntime(
        subgoal_runtime_factory=lambda _scope, _subgoal: BrokenRuntime()
    )

    state = runtime.run("Research Apple", workflow_kind="generic_research")

    assert state.status == "failed"
    assert state.fallback_events
    assert state.decisions[-1].stop_reason == "tool_failures"


def test_global_agent_runtime_needs_review_when_no_evidence_accepted() -> None:
    event = ToolExecutionEvent(
        event_id="event-empty",
        round_id="round-0",
        tool_call_id="call-empty",
        tool_name="web_search",
        arguments={},
        status="success",
        result_summary=json.dumps({"tool": "web_search", "data": {"results": []}}),
        latency_ms=1,
        result_chars=20,
        created_at=utcnow(),
    )
    runtime = GlobalAgentRuntime(
        subgoal_runtime_factory=lambda _scope, _subgoal: FakeRuntime([event])
    )

    state = runtime.run("Research Apple", workflow_kind="generic_research")

    assert state.status == "needs_review"
    assert state.decisions[-1].stop_reason == "human_review_required"
    assert state.evidence_candidates[0]["status"] == "rejected"


def test_global_agent_runtime_needs_review_when_no_tools_run() -> None:
    runtime = GlobalAgentRuntime(
        subgoal_runtime_factory=lambda _scope, _subgoal: FakeRuntime([])
    )

    state = runtime.run("Research Apple", workflow_kind="generic_research")

    assert state.status == "needs_review"
    assert state.decisions[-1].stop_reason == "human_review_required"
    assert state.human_review_items
    assert state.human_review_items[0].object_type == "report_claim"
    assert any("produced no tool evidence" in event for event in state.fallback_events)


def test_global_agent_runtime_factory_receives_scope_and_subgoal() -> None:
    calls: list[tuple[str, AgentSubgoal]] = []

    def factory(scope: str, subgoal: AgentSubgoal) -> FakeRuntime:
        calls.append((scope, subgoal))
        return FakeRuntime([_web_event()])

    GlobalAgentRuntime(subgoal_runtime_factory=factory).run(
        "Research Apple",
        workflow_kind="generic_research",
    )

    assert calls
    assert calls[0][0] == "company_research"
    assert isinstance(calls[0][1], AgentSubgoal)
