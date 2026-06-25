"""Tests for the AgentRuntime orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.agents.critic import CriticAgent
from src.agents.runtime import AgentRuntime
from src.agents.state import AgentState, ToolCall
from src.agents.tools import Tool, ToolRegistry


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


class FakeAgent:
    """Minimal Agent that tags ``state.notes`` with its name."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, state: AgentState) -> AgentState:
        state.notes.append(f"agent:{self.name}")
        return state


class FailingAgent:
    name = "boom"

    def run(self, state: AgentState) -> AgentState:  # pragma: no cover - raised
        raise RuntimeError("kaboom")


class EchoTool:
    name = "echo"

    def call(self, **kwargs: Any) -> dict[str, Any]:
        return {"echo": kwargs}


class FlakyTool:
    name = "flaky"

    def call(self, **kwargs: Any) -> dict[str, Any]:  # pragma: no cover - raised
        raise ValueError("explode")


# ---------------------------------------------------------------------------
# runtime behavior
# ---------------------------------------------------------------------------


def test_runtime_respects_max_steps() -> None:
    runtime = AgentRuntime(max_steps=2)  # type: ignore[arg-type]
    state = AgentState(goal="x", ticker="AAPL")
    out = runtime.run(goal=state.goal, ticker=state.ticker)
    # Planner always emits fetch_filing + discover_opportunity + finish when
    # starting from an empty state with a ticker, so the runtime should
    # either stop on max_steps or on finish - whichever comes first.
    assert out.current_step <= 2
    assert any("max_steps" in n or "finish" in n for n in out.notes)


def test_runtime_records_tool_history() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    runtime = AgentRuntime(tools=registry)
    out = runtime.run(goal="explore healthcare trends")
    # No ticker means planner starts with web_search, which is a tool action.
    assert out.tool_history, "expected at least one tool call recorded"
    assert all(isinstance(call, ToolCall) for call in out.tool_history)
    assert out.tool_history[0].tool_name in {"web_search"}


def test_runtime_handles_agent_failure_gracefully() -> None:
    agents = {
        "filing_fetcher": FailingAgent(),
    }
    runtime = AgentRuntime(agents=agents)
    out = runtime.run(goal="x", ticker="AAPL")
    assert any("filing_fetcher" in n and "failed" in n for n in out.notes)
    # Runtime should not raise; final state should still exist.
    assert isinstance(out, AgentState)


def test_runtime_handles_tool_failure_gracefully() -> None:
    registry = ToolRegistry()
    registry.register(FlakyTool())
    runtime = AgentRuntime(tools=registry)
    out = runtime.run(goal="explore healthcare trends")
    # Web search is a tool action in the default plan.
    flaky_calls = [c for c in out.tool_history if c.tool_name == "flaky"]
    assert flaky_calls == []
    # But the failure of the "web_search" tool should be recorded as a note.
    assert any("web_search" in n and "failed" in n for n in out.notes)


def test_runtime_unknown_tool_returns_failed_result() -> None:
    """Tools map fallback: unknown tool action is a failure, not a crash."""
    runtime = AgentRuntime()
    # Force a plan with a tool action by calling the planner directly.
    out = runtime.run(goal="explore healthcare trends")
    web_calls = [c for c in out.tool_history if c.tool_name == "web_search"]
    assert web_calls, "expected runtime to attempt web_search"
    assert web_calls[0].success is False
    assert web_calls[0].created_at <= datetime.now(timezone.utc)


def test_runtime_applies_critic_at_end() -> None:
    runtime = AgentRuntime(critic=CriticAgent())
    out = runtime.run(goal="x", ticker="AAPL")
    # The critic should be a no-op on an empty state; no claims were created.
    # But the runtime should still have completed without raising.
    assert isinstance(out, AgentState)


def test_runtime_runs_end_to_end_with_fake_agents() -> None:
    agents = {
        "filing_fetcher": FakeAgent("filing_fetcher"),
        "entity_extractor": FakeAgent("entity_extractor"),
        "relation_extractor": FakeAgent("relation_extractor"),
        "graph_writer": FakeAgent("graph_writer"),
        "opportunity_discoverer": FakeAgent("opportunity_discoverer"),
    }
    runtime = AgentRuntime(agents=agents)
    out = runtime.run(goal="analyze AAPL", ticker="AAPL")
    agent_notes = [n for n in out.notes if n.startswith("agent:")]
    # At least the discover_opportunity agent should always run.
    assert "agent:opportunity_discoverer" in agent_notes
    assert all(isinstance(n, str) for n in out.notes)
