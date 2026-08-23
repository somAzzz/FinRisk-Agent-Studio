"""Translate project Agent budgets into Pydantic AI usage limits."""

from pydantic_ai import UsageLimits

from src.agents.state import AgentBudget


def build_usage_limits(budget: AgentBudget) -> UsageLimits:
    """Preserve project request/tool-call limits at the framework boundary."""
    request_limit = budget.max_subgoals * (
        budget.max_tool_rounds_per_subgoal + 1
    )
    return UsageLimits(
        request_limit=max(1, request_limit),
        tool_calls_limit=budget.max_total_tool_calls,
    )


__all__ = ["build_usage_limits"]
