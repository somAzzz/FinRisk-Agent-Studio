"""Tests for the V21 local agent-run API."""

from __future__ import annotations

import asyncio
import json

import pytest

from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.llm_runtime import LLMToolRunResult
from src.agents.state import AgentRunState
from src.api.store_factory import get_agent_run_store
from src.api.agent_runs import (
    AgentRunRequest,
    HumanReviewActionRequest,
    build_agent_runtime,
    get_agent_run,
    get_agent_run_timeline,
    list_agent_runs,
    reset_agent_run_store_for_tests,
    review_agent_evidence_candidate,
    review_agent_run_item,
    set_agent_runtime_for_tests,
    start_agent_run,
)
from src.schemas.tool_trace import ToolExecutionEvent
from src.workflows.state import utcnow


@pytest.fixture(autouse=True)
def _reset_agent_runs() -> None:
    reset_agent_run_store_for_tests()
    yield
    reset_agent_run_store_for_tests()


def _review_event() -> ToolExecutionEvent:
    payload = {
        "tool": "web_search",
        "status": "success",
        "data": {
            "query": "Apple supply chain",
            "results": [
                {
                    "title": "Weakly related source",
                    "url": "https://example.com/source",
                    "snippet": "This page discusses an unrelated topic.",
                    "rank": 1,
                }
            ],
        },
    }
    return ToolExecutionEvent(
        event_id="event-review",
        round_id="round-0",
        tool_call_id="call-review",
        tool_name="web_search",
        arguments={"query": "Apple supply chain"},
        status="success",
        result_summary=json.dumps(payload),
        latency_ms=1,
        result_chars=100,
        created_at=utcnow(),
    )


def _accepted_event() -> ToolExecutionEvent:
    payload = {
        "tool": "web_search",
        "status": "success",
        "data": {
            "query": "Apple supply chain",
            "results": [
                {
                    "title": "Apple supply chain source",
                    "url": "https://example.com/apple-supply-chain",
                    "snippet": (
                        "Identify filing backed risks for Assess Apple supply "
                        "chain risk using supplier evidence."
                    ),
                    "rank": 1,
                }
            ],
        },
    }
    return ToolExecutionEvent(
        event_id="event-accepted",
        round_id="round-0",
        tool_call_id="call-accepted",
        tool_name="web_search",
        arguments={"query": "Apple supply chain"},
        status="success",
        result_summary=json.dumps(payload),
        latency_ms=1,
        result_chars=100,
        created_at=utcnow(),
    )


async def _wait_for_terminal(run_id: str, attempts: int = 20):
    for _ in range(attempts):
        state = await get_agent_run(run_id)
        if state.status in {"completed", "failed", "needs_review"}:
            return state
        await asyncio.sleep(0.05)
    return await get_agent_run(run_id)


async def test_start_agent_run_get_timeline_and_review_item() -> None:
    class Runtime:
        def run(self, goal: str) -> LLMToolRunResult:
            return LLMToolRunResult(
                goal=goal,
                final_answer="needs review",
                tool_events=[_review_event()],
            )

    set_agent_runtime_for_tests(
        GlobalAgentRuntime(subgoal_runtime_factory=lambda _scope, _subgoal: Runtime())
    )

    summary = await start_agent_run(
        AgentRunRequest(
            goal="Assess Apple supply chain risk",
            workflow_kind="finrisk",
        )
    )

    assert summary.run_id.startswith("agent-")
    assert summary.status == "queued"
    state = await _wait_for_terminal(summary.run_id)
    assert state.status == "needs_review"

    timeline = await get_agent_run_timeline(summary.run_id)
    assert timeline.decisions
    assert timeline.subgoals
    assert timeline.tool_events
    assert timeline.evidence_candidates
    assert len(timeline.human_review_items) == 1

    item_id = timeline.human_review_items[0]["item_id"]
    reviewed = await review_agent_run_item(
        summary.run_id,
        item_id,
        HumanReviewActionRequest(
            action="approve",
            reviewer_comment="Source is acceptable for the local test.",
        ),
    )
    state = await get_agent_run(summary.run_id)

    assert reviewed.status == "approved"
    assert reviewed.object_id in state.accepted_evidence_ids
    assert state.status == "completed"


async def test_review_evidence_candidate_directly() -> None:
    class Runtime:
        def run(self, goal: str) -> LLMToolRunResult:
            return LLMToolRunResult(
                goal=goal,
                final_answer="needs review",
                tool_events=[_review_event()],
            )

    set_agent_runtime_for_tests(
        GlobalAgentRuntime(subgoal_runtime_factory=lambda _scope, _subgoal: Runtime())
    )

    summary = await start_agent_run(
        AgentRunRequest(
            goal="Assess Apple supply chain risk",
            workflow_kind="finrisk",
        )
    )
    await _wait_for_terminal(summary.run_id)
    timeline = await get_agent_run_timeline(summary.run_id)
    candidate_id = timeline.evidence_candidates[0]["candidate_id"]

    reviewed = await review_agent_evidence_candidate(
        summary.run_id,
        candidate_id,
        HumanReviewActionRequest(action="approve"),
    )
    state = await get_agent_run(summary.run_id)

    assert reviewed["status"] == "accepted"
    assert candidate_id in state.accepted_evidence_ids


async def test_list_agent_runs_returns_recent_runs() -> None:
    class Runtime:
        def run(self, goal: str) -> LLMToolRunResult:
            return LLMToolRunResult(
                goal=goal,
                final_answer="done",
                tool_events=[_accepted_event()],
            )

    set_agent_runtime_for_tests(
        GlobalAgentRuntime(subgoal_runtime_factory=lambda _scope, _subgoal: Runtime())
    )

    first = await start_agent_run(AgentRunRequest(goal="first"))
    second = await start_agent_run(AgentRunRequest(goal="second"))
    await _wait_for_terminal(first.run_id)
    await _wait_for_terminal(second.run_id)

    recent = await list_agent_runs(limit=1)

    assert len(recent) == 1
    assert recent[0].run_id == second.run_id


async def test_agent_runs_can_persist_with_sqlite(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RUN_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("RUN_STORE_DB", str(tmp_path / "runs.sqlite3"))
    reset_agent_run_store_for_tests()

    state = AgentRunState(
        run_id="agent-persisted",
        user_goal="Persist this agent run",
        workflow_kind="finrisk",
        status="completed",
    )
    await get_agent_run_store().update(state)

    assert (await list_agent_runs(limit=10))[0].run_id == "agent-persisted"

    get_agent_run_store.cache_clear()
    persisted = await list_agent_runs(limit=10)

    assert persisted[0].run_id == "agent-persisted"
    assert persisted[0].status == "completed"


async def test_start_agent_run_uses_default_runtime_factory(monkeypatch) -> None:
    class Runtime:
        def run(self, goal: str, **kwargs) -> object:
            state = GlobalAgentRuntime(
                subgoal_runtime_factory=lambda _scope, _subgoal: self
            ).planner.initialize(
                user_goal=goal,
                workflow_kind=kwargs["workflow_kind"],
            )
            state.status = "completed"
            return state

    called = False

    def fake_build_runtime(request: AgentRunRequest) -> Runtime:
        nonlocal called
        called = True
        assert request.provider == "vllm"
        return Runtime()

    monkeypatch.setattr("src.api.agent_runs.build_agent_runtime", fake_build_runtime)

    summary = await start_agent_run(
        AgentRunRequest(
            goal="Assess Apple supply chain risk",
            workflow_kind="finrisk",
            provider="vllm",
        )
    )

    assert summary.status == "queued"
    state = await _wait_for_terminal(summary.run_id)
    assert called
    assert state.status == "completed"


def test_build_agent_runtime_passes_request_options_to_tool_runtime(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class Runtime:
        def run(self, goal: str) -> LLMToolRunResult:
            return LLMToolRunResult(
                goal=goal,
                final_answer="done",
                tool_events=[_accepted_event()],
            )

    def fake_build_runtime(**kwargs) -> Runtime:
        captured.update(kwargs)
        return Runtime()

    monkeypatch.setattr(
        "src.pipelines.llm_tool_research.build_runtime",
        fake_build_runtime,
    )

    runtime = build_agent_runtime(
        AgentRunRequest(
            goal="Assess Apple supply chain risk",
            workflow_kind="finrisk",
            provider="vllm",
            tool_loop_mode="auto",
            tool_scope="supply_chain",
            max_tool_rounds=2,
            model="local-model",
            base_url="http://localhost:8000/v1",
        )
    )
    state = runtime.run("Assess Apple supply chain risk", workflow_kind="finrisk")

    assert state.status == "completed"
    assert captured == {
        "provider": "vllm",
        "tools_scope": "supply_chain",
        "max_tool_rounds": 2,
        "model": "local-model",
        "base_url": "http://localhost:8000/v1",
        "tool_loop_mode": "auto",
        "tool_choice": "required",
    }


def test_build_agent_runtime_does_not_force_json_fallback_tool_choice(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class Runtime:
        def run(self, goal: str) -> LLMToolRunResult:
            return LLMToolRunResult(
                goal=goal,
                final_answer="done",
                tool_events=[_accepted_event()],
            )

    def fake_build_runtime(**kwargs) -> Runtime:
        captured.update(kwargs)
        return Runtime()

    monkeypatch.setattr(
        "src.pipelines.llm_tool_research.build_runtime",
        fake_build_runtime,
    )

    runtime = build_agent_runtime(
        AgentRunRequest(
            goal="Assess Apple supply chain risk",
            workflow_kind="finrisk",
            provider="sglang",
            tool_loop_mode="json_fallback",
        )
    )
    state = runtime.run("Assess Apple supply chain risk", workflow_kind="finrisk")

    assert state.status == "completed"
    assert captured["tool_choice"] == "auto"


def test_tool_research_sglang_uses_local_defaults(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class Client:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    class Catalog:
        pass

    def build_catalog(*, scope):
        return Catalog()

    monkeypatch.delenv("SGLANG_BASE_URL", raising=False)
    monkeypatch.delenv("SGLANG_MODEL", raising=False)
    monkeypatch.setattr("src.llm.client.EdgarLLMClient", Client)
    monkeypatch.setattr(
        "src.pipelines.llm_tool_research.build_project_tool_catalog",
        build_catalog,
    )

    from src.pipelines.llm_tool_research import build_runtime

    build_runtime(
        provider="sglang",
        tools_scope="company_research",
        max_tool_rounds=1,
    )

    assert captured["base_url"] == "http://localhost:30000/v1"
    assert captured["model"] == "Qwen/Qwen3.5-35B-A3B"
    assert captured["provider"] == "sglang"
