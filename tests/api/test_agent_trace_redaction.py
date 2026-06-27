"""Trace redaction tests for the V21 agent-run API."""

from __future__ import annotations

import json

import pytest

from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.llm_runtime import LLMToolRunResult
from src.api.agent_runs import (
    AgentRunRequest,
    get_agent_run_trace,
    reset_agent_run_store_for_tests,
    set_agent_runtime_for_tests,
    start_agent_run,
)
from src.schemas.tool_trace import ToolExecutionEvent
from src.workflows.state import utcnow

API_SECRET = "sk-abcdefghijklmnopqrstuvwxyz1234567890"
BEARER_SECRET = "Bearer abcdefghijklmnopqrstuvwxyz1234567890"


@pytest.fixture(autouse=True)
def _reset_agent_runs() -> None:
    reset_agent_run_store_for_tests()
    yield
    reset_agent_run_store_for_tests()


def _secret_event() -> ToolExecutionEvent:
    payload = {
        "tool": "web_search",
        "status": "success",
        "data": {
            "query": "Apple supply chain",
            "results": [
                {
                    "title": "Apple source",
                    "url": "https://example.com/source",
                    "snippet": f"Apple supply chain risk token {API_SECRET}",
                    "rank": 1,
                }
            ],
        },
    }
    return ToolExecutionEvent(
        event_id="event-secret",
        round_id="round-0",
        tool_call_id="call-secret",
        tool_name="web_search",
        arguments={"query": "Apple supply chain", "authorization": BEARER_SECRET},
        status="success",
        result_summary=json.dumps(payload),
        latency_ms=1,
        result_chars=100,
        created_at=utcnow(),
    )


async def test_agent_trace_json_redacts_tool_arguments_and_results() -> None:
    class Runtime:
        def run(self, goal: str) -> LLMToolRunResult:
            return LLMToolRunResult(
                goal=goal,
                final_answer=f"answer with {API_SECRET}",
                tool_events=[_secret_event()],
            )

    set_agent_runtime_for_tests(
        GlobalAgentRuntime(subgoal_runtime_factory=lambda _scope, _subgoal: Runtime())
    )
    summary = await start_agent_run(
        AgentRunRequest(goal="Assess Apple supply chain risk", workflow_kind="finrisk")
    )

    trace = await get_agent_run_trace(summary.run_id)
    encoded = json.dumps(trace)

    assert API_SECRET not in encoded
    assert BEARER_SECRET not in encoded
    assert "[API_KEY]" in encoded
    assert "[TOKEN]" in encoded
