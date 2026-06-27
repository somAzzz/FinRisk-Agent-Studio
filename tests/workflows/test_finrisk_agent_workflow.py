"""Tests for the V21 FinRisk agent workflow wrapper."""

from __future__ import annotations

import json
from pathlib import Path

from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.llm_runtime import LLMToolRunResult
from src.schemas.tool_trace import ToolExecutionEvent
from src.workflows.finrisk_agent_workflow import run_finrisk_agent_workflow
from src.workflows.state import FinRiskRequest, utcnow

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "finrisk"
    / "aapl_demo_workflow.json"
)


def _request() -> FinRiskRequest:
    return FinRiskRequest(
        ticker="AAPL",
        analysis_goal="Assess Apple supply chain risk",
        demo_mode=True,
    )


def _event() -> ToolExecutionEvent:
    payload = {
        "tool": "web_search",
        "status": "success",
        "data": {
            "query": "Apple supply chain",
            "results": [
                {
                    "title": "Apple supply chain",
                    "url": "https://example.com/apple",
                    "snippet": "Apple supply chain risk affects supplier planning.",
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
        arguments={"query": "Apple supply chain"},
        status="success",
        result_summary=json.dumps(payload),
        latency_ms=1,
        result_chars=100,
        created_at=utcnow(),
    )


async def test_finrisk_agent_plan_only_preserves_demo_workflow_output() -> None:
    result = await run_finrisk_agent_workflow(
        _request(),
        fixture_path=FIXTURE_PATH,
        agent_mode="plan_only",
    )

    assert result.mode == "plan_only"
    assert result.agent_state.workflow_kind == "finrisk"
    assert result.agent_state.subgoals
    assert result.workflow_state.report is not None
    assert result.workflow_state.request.ticker == "AAPL"


async def test_finrisk_agent_shadow_runs_global_runtime_without_replacing_workflow() -> None:
    class Runtime:
        def run(self, goal: str) -> LLMToolRunResult:
            return LLMToolRunResult(
                goal=goal,
                final_answer="done",
                tool_events=[_event()],
            )

    agent_runtime = GlobalAgentRuntime(
        subgoal_runtime_factory=lambda _scope, _subgoal: Runtime()
    )

    result = await run_finrisk_agent_workflow(
        _request(),
        fixture_path=FIXTURE_PATH,
        agent_mode="shadow",
        agent_runtime=agent_runtime,
    )

    assert result.agent_state.status == "completed"
    assert result.agent_state.tool_traces
    assert result.agent_state.evidence_candidates
    assert result.workflow_state.report is not None
