"""The orchestrator that ties planner, agents, and tools together."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.agents.base import Agent
from src.agents.critic import CriticAgent
from src.agents.planner import PlannerAgent, PlanStepAction
from src.agents.state import AgentState, ToolCall
from src.agents.tools import ToolRegistry

# Map a plan step action to the agent name that should execute it. Steps
# without an agent (e.g. ``finish``) are handled directly by the runtime.
_ACTION_AGENT_MAP: dict[PlanStepAction, str] = {
    "fetch_filing": "filing_fetcher",
    "fetch_transcript": "transcript_fetcher",
    "web_search": "web_searcher",
    "extract_entities": "entity_extractor",
    "extract_relations": "relation_extractor",
    "write_graph": "graph_writer",
    "analyze_risk": "risk_analyzer",
    "analyze_sentiment": "sentiment_analyzer",
    "discover_opportunity": "opportunity_discoverer",
}


class AgentRuntime:
    """Run a planner-generated plan end-to-end against a set of agents."""

    def __init__(
        self,
        agents: dict[str, Agent] | None = None,
        tools: ToolRegistry | None = None,
        planner: PlannerAgent | None = None,
        critic: CriticAgent | None = None,
        max_steps: int | None = None,
    ) -> None:
        self.agents: dict[str, Agent] = dict(agents or {})
        self.tools: ToolRegistry = tools or ToolRegistry()
        self.planner: PlannerAgent = planner or PlannerAgent()
        self.critic: CriticAgent = critic or CriticAgent()
        self._max_steps_override: int | None = max_steps

    def register_agent(self, name: str, agent: Agent) -> None:
        """Register an additional agent at runtime."""
        self.agents[name] = agent

    def run(self, goal: str, ticker: str | None = None) -> AgentState:
        """Execute a single end-to-end run for ``goal``."""
        state = AgentState(goal=goal, ticker=ticker)
        if self._max_steps_override is not None:
            state.max_steps = self._max_steps_override
        plan = self.planner.plan(state)

        for step in plan.steps:
            if state.current_step >= state.max_steps:
                state.notes.append(
                    "runtime: max_steps reached, halting execution"
                )
                break

            if step.action == "finish":
                state.notes.append("runtime: plan reached finish step")
                break

            state.current_step += 1
            state = self._execute_step(state, step)

        # Always apply the critic to the final state.
        try:
            state = self.critic.run(state)
        except Exception as exc:
            state.notes.append(
                f"runtime: critic failed ({type(exc).__name__}: {exc})"
            )

        return state

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _execute_step(self, state: AgentState, step: Any) -> AgentState:
        """Dispatch a single plan step to an agent or tool.

        Tool-flavoured actions (``fetch_filing``, ``fetch_transcript``,
        ``web_search``) prefer the agent map (so tests / custom runtimes
        can register a fake agent for these actions) and fall back to the
        :class:`ToolRegistry`. If neither is registered, the registry still
        records a failed tool call. Analytical actions always go through
        the agent map; ``finish`` is handled by the caller.
        """
        action = step.action
        if action in {"fetch_filing", "fetch_transcript", "web_search"}:
            agent_name = _ACTION_AGENT_MAP.get(action)
            if agent_name is not None and agent_name in self.agents:
                return self._execute_agent(state, step)
            return self._execute_tool(state, step)
        return self._execute_agent(state, step)

    def _execute_tool(self, state: AgentState, step: Any) -> AgentState:
        result = self.tools.call(step.action, **step.inputs)
        call = ToolCall(
            tool_name=step.action,
            arguments=dict(step.inputs),
            result_summary=_summarize(result.content),
            success=result.success,
            created_at=datetime.now(UTC),
        )
        state.tool_history.append(call)
        if not result.success:
            state.notes.append(
                f"runtime: tool {step.action} failed ({result.error})"
            )
        return state

    def _execute_agent(self, state: AgentState, step: Any) -> AgentState:
        agent_name = _ACTION_AGENT_MAP.get(step.action)
        if agent_name is None:
            state.notes.append(
                f"runtime: no agent mapping for action {step.action!r}, skipping"
            )
            return state

        agent = self.agents.get(agent_name)
        if agent is None:
            state.notes.append(
                f"runtime: no agent registered for action {step.action!r} "
                f"(expected {agent_name!r})"
            )
            return state

        try:
            state = agent.run(state)
        except Exception as exc:
            state.notes.append(
                f"runtime: agent {agent_name!r} failed "
                f"({type(exc).__name__}: {exc})"
            )
        return state


def _summarize(content: Any) -> str | None:
    """Return a short, JSON-serializable summary of a tool result."""
    if content is None:
        return None
    if isinstance(content, str):
        return content[:200]
    return repr(content)[:200]
