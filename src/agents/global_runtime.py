"""Global V21 agent runtime with planner-driven subgoal execution."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Protocol

from src.agents.context import AgentContextBuilder
from src.agents.planner import AgentPlanner
from src.agents.state import (
    AgentBudget,
    AgentRunState,
    AgentSubgoal,
    AgentWorkflowKind,
)
from src.ai.runtime_types import LLMToolRunResult
from src.evidence import EvidenceCandidateNormalizer


class SubgoalRuntime(Protocol):
    """Runtime capable of executing one subgoal objective."""

    def run(self, goal: str) -> LLMToolRunResult:
        """Execute ``goal`` and return typed Agent results."""


SubgoalRuntimeFactory = Callable[..., SubgoalRuntime]


class GlobalAgentRuntime:
    """Coordinate planner decisions, subgoal tool runs, and evidence ingestion."""

    def __init__(
        self,
        *,
        planner: AgentPlanner | None = None,
        subgoal_runtime_factory: SubgoalRuntimeFactory,
        evidence_normalizer: EvidenceCandidateNormalizer | None = None,
        context_builder: AgentContextBuilder | None = None,
    ) -> None:
        self.planner = planner or AgentPlanner()
        self.subgoal_runtime_factory = subgoal_runtime_factory
        self.evidence_normalizer = evidence_normalizer or EvidenceCandidateNormalizer()
        self.context_builder = context_builder

    def run(
        self,
        user_goal: str,
        *,
        workflow_kind: AgentWorkflowKind = "generic_research",
        budget: AgentBudget | None = None,
        subject: dict | None = None,
        run_id: str | None = None,
        conversation_id: str | None = None,
    ) -> AgentRunState:
        """Run an agent task through the canonical Pydantic Graph."""
        from src.ai.graphs.global_agent import (
            GlobalAgentGraphDeps,
            GlobalAgentGraphInput,
            run_global_agent_graph,
        )
        from src.ai.runtime_adapter import run_awaitable_sync

        return run_awaitable_sync(
            run_global_agent_graph(
                GlobalAgentGraphInput(
                    user_goal=user_goal,
                    workflow_kind=workflow_kind,
                    budget=budget,
                    subject=subject,
                    run_id=run_id,
                    conversation_id=conversation_id,
                ),
                deps=GlobalAgentGraphDeps(
                    planner=self.planner,
                    subgoal_runtime_factory=self.subgoal_runtime_factory,
                    evidence_normalizer=self.evidence_normalizer,
                    context_builder=self.context_builder,
                ),
            )
        )


def _create_subgoal_runtime(
    factory: SubgoalRuntimeFactory,
    tool_scope: str,
    subgoal: AgentSubgoal,
    state: AgentRunState,
) -> SubgoalRuntime:
    """Pass full run context to new factories while preserving old callables."""
    try:
        parameters = inspect.signature(factory).parameters.values()
    except (TypeError, ValueError):
        return factory(tool_scope, subgoal)
    accepts_state = any(
        parameter.kind is inspect.Parameter.VAR_POSITIONAL
        for parameter in parameters
    ) or sum(
        parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }
        for parameter in parameters
    ) >= 3
    if accepts_state:
        return factory(tool_scope, subgoal, state)
    return factory(tool_scope, subgoal)


__all__ = [
    "GlobalAgentRuntime",
    "SubgoalRuntime",
    "SubgoalRuntimeFactory",
]
