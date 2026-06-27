"""Read-first context integration for V21 agent runs."""

from __future__ import annotations

from typing import Any

from src.agents.state import AgentWorkflowKind
from src.memory.context_manager import ContextManager
from src.memory.models import ContextPack


class AgentContextBuilder:
    """Build bounded memory context for planner/runtime initialization."""

    def __init__(self, context_manager: ContextManager) -> None:
        self.context_manager = context_manager

    def build(
        self,
        *,
        run_id: str,
        user_goal: str,
        workflow_kind: AgentWorkflowKind,
        subject: dict[str, Any] | None = None,
        token_budget: int = 4000,
    ) -> ContextPack:
        """Build a read-only context pack for an agent run."""
        return self.context_manager.build(
            run_id=run_id,
            step_name="agent_planner",
            task=user_goal,
            subject=subject or {},
            intent=workflow_kind,
            token_budget=token_budget,
            objective=user_goal,
        )


__all__ = ["AgentContextBuilder"]
