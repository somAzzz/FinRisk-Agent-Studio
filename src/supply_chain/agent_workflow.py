"""V21 supply-chain agent workflow wrapper."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.planner import AgentPlanner
from src.agents.state import AgentRunState
from src.supply_chain.models import SupplyChainExploreRequest, SupplyChainExploreState
from src.supply_chain.workflow import run_supply_chain_workflow

SupplyChainAgentMode = Literal["plan_only", "shadow", "primary"]


class SupplyChainAgentWorkflowResult(BaseModel):
    """Combined result for V21 supply-chain agent runs."""

    model_config = ConfigDict(extra="forbid")

    agent_state: AgentRunState
    workflow_state: SupplyChainExploreState
    mode: SupplyChainAgentMode = "plan_only"


async def run_supply_chain_agent_workflow(
    request: SupplyChainExploreRequest,
    *,
    agent_runtime: GlobalAgentRuntime | None = None,
    agent_mode: SupplyChainAgentMode = "plan_only",
    steps: list[Any] | None = None,
    initial_state: SupplyChainExploreState | None = None,
    store: dict | None = None,
) -> SupplyChainAgentWorkflowResult:
    """Run the V21 supply-chain agent wrapper and existing workflow.

    `plan_only` records the planner's default supply-chain subgoals without
    executing tools. `shadow` executes the supplied global runtime before the
    existing v18 workflow while preserving the workflow's deterministic final
    Sankey output. `primary` is reserved for later replacement milestones and
    currently follows the same compatibility behavior as `shadow`.
    """
    user_goal = _request_goal(request)
    if agent_mode == "plan_only" or agent_runtime is None:
        agent_state = AgentPlanner().initialize(
            user_goal=user_goal,
            workflow_kind="supply_chain",
        )
    else:
        agent_state = agent_runtime.run(
            user_goal,
            workflow_kind="supply_chain",
        )
    workflow_state = await run_supply_chain_workflow(
        request,
        steps=steps,
        initial_state=initial_state,
        store=store,
    )
    return SupplyChainAgentWorkflowResult(
        agent_state=agent_state,
        workflow_state=workflow_state,
        mode=agent_mode,
    )


def _request_goal(request: SupplyChainExploreRequest) -> str:
    subject = request.company_name or request.ticker or "the company"
    return (
        f"Explore the supply chain for {subject} product {request.product_name}; "
        f"max depth {request.max_depth}, max suppliers per node "
        f"{request.max_suppliers_per_node}."
    )


__all__ = [
    "SupplyChainAgentMode",
    "SupplyChainAgentWorkflowResult",
    "run_supply_chain_agent_workflow",
]
