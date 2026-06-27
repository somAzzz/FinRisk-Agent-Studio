"""Tests for the V21 supply-chain agent workflow wrapper."""

from __future__ import annotations

import json

from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.llm_runtime import LLMToolRunResult
from src.schemas.tool_trace import ToolExecutionEvent
from src.supply_chain.agent_workflow import run_supply_chain_agent_workflow
from src.supply_chain.models import SupplyChainExploreRequest
from src.workflows.state import utcnow


def _request() -> SupplyChainExploreRequest:
    return SupplyChainExploreRequest(
        company_name="OpenAI",
        product_name="ChatGPT",
        max_depth=3,
        demo_mode=True,
        cached_mode=True,
    )


def _event() -> ToolExecutionEvent:
    payload = {
        "tool": "web_search",
        "status": "success",
        "data": {
            "query": "OpenAI ChatGPT suppliers",
            "results": [
                {
                    "title": "ChatGPT infrastructure suppliers",
                    "url": "https://example.com/chatgpt-supply-chain",
                    "snippet": (
                        "Discover supplier candidates for OpenAI ChatGPT supply "
                        "chain max depth three max suppliers per node five: "
                        "compute, networking, and data-center power suppliers."
                    ),
                    "rank": 1,
                }
            ],
        },
    }
    return ToolExecutionEvent(
        event_id="sc-event-1",
        round_id="round-0",
        tool_call_id="sc-call-1",
        tool_name="web_search",
        arguments={"query": "OpenAI ChatGPT suppliers"},
        status="success",
        result_summary=json.dumps(payload),
        latency_ms=1,
        result_chars=100,
        created_at=utcnow(),
    )


async def test_supply_chain_agent_plan_only_preserves_demo_workflow_output() -> None:
    result = await run_supply_chain_agent_workflow(
        _request(),
        agent_mode="plan_only",
        store={},
    )

    assert result.mode == "plan_only"
    assert result.agent_state.workflow_kind == "supply_chain"
    assert result.agent_state.subgoals
    assert result.workflow_state.status == "completed"
    assert result.workflow_state.sankey is not None


async def test_supply_chain_agent_shadow_runs_global_runtime_without_replacing_workflow() -> None:
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

    result = await run_supply_chain_agent_workflow(
        _request(),
        agent_mode="shadow",
        agent_runtime=agent_runtime,
        store={},
    )

    assert result.agent_state.status == "completed"
    assert result.agent_state.tool_traces
    assert result.agent_state.evidence_candidates
    assert result.workflow_state.status == "completed"
    assert result.workflow_state.sankey is not None
