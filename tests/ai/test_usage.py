"""Budget translation tests for Pydantic AI usage limits."""

from src.agents.state import AgentBudget
from src.ai.usage import build_usage_limits


def test_agent_budget_maps_to_framework_usage_limits() -> None:
    limits = build_usage_limits(
        AgentBudget(
            max_subgoals=3,
            max_tool_rounds_per_subgoal=2,
            max_total_tool_calls=7,
        )
    )

    assert limits.request_limit == 9
    assert limits.tool_calls_limit == 7
