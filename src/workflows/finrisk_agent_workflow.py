"""V21 FinRisk agent workflow wrapper.

This module connects the global agent runtime to the existing FinRisk
workflow without replacing the deterministic workflow output path yet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.planner import AgentPlanner
from src.agents.state import AgentRunState
from src.workflows.finrisk_workflow import run_finrisk_workflow
from src.workflows.state import FinRiskRequest, FinRiskWorkflowState

FinRiskAgentMode = Literal["plan_only", "shadow", "primary"]


class FinRiskAgentWorkflowResult(BaseModel):
    """Combined result for V21 FinRisk agent runs."""

    model_config = ConfigDict(extra="forbid")

    agent_state: AgentRunState
    workflow_state: FinRiskWorkflowState
    mode: FinRiskAgentMode = "plan_only"


async def run_finrisk_agent_workflow(
    request: FinRiskRequest,
    *,
    agent_runtime: GlobalAgentRuntime | None = None,
    agent_mode: FinRiskAgentMode = "plan_only",
    fixture_path: Path | None = None,
    steps: Any = None,
    run_id: str | None = None,
    initial_state: FinRiskWorkflowState | None = None,
    quality_engine: Any | None = None,
    quality_gated: bool = False,
) -> FinRiskAgentWorkflowResult:
    """Run the V21 FinRisk agent wrapper and existing workflow.

    `plan_only` creates an auditable `AgentRunState` without executing tools.
    `shadow` executes the supplied global agent runtime before the existing
    workflow, but the existing workflow remains the source of final output.
    `primary` is reserved for later V21 milestones; for now it behaves like
    `shadow` while preserving deterministic workflow writes.
    """
    if agent_mode == "plan_only" or agent_runtime is None:
        agent_state = AgentPlanner().initialize(
            user_goal=request.analysis_goal,
            workflow_kind="finrisk",
        )
    else:
        agent_state = agent_runtime.run(
            request.analysis_goal,
            workflow_kind="finrisk",
        )
    workflow_state = await run_finrisk_workflow(
        request,
        fixture_path=fixture_path,
        steps=steps,
        run_id=run_id,
        initial_state=initial_state,
        quality_engine=quality_engine,
        quality_gated=quality_gated,
    )
    return FinRiskAgentWorkflowResult(
        agent_state=agent_state,
        workflow_state=workflow_state,
        mode=agent_mode,
    )


__all__ = [
    "FinRiskAgentMode",
    "FinRiskAgentWorkflowResult",
    "run_finrisk_agent_workflow",
]
