"""Production adapter for the typed Pydantic AI planner Agent."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from pydantic_ai.models import Model

from src.agents.state import AgentRunState, AgentRunTrace
from src.ai.agents.structured import build_planner_agent
from src.ai.deps import (
    AgentDeps,
    AgentPermissions,
    AgentServices,
    AgentSubject,
)
from src.ai.runtime_adapter import run_awaitable_sync
from src.config import Settings
from src.tools.contracts import ToolCatalog


class PydanticAIPlanner:
    """Callable accepted by the existing AgentPlanner fallback boundary."""

    def __init__(
        self,
        *,
        model: Model,
        settings: Settings,
        tool_catalog: ToolCatalog,
        services: AgentServices | None = None,
    ) -> None:
        self.agent = build_planner_agent(model)
        self.settings = settings
        self.tool_catalog = tool_catalog
        self.services = services or AgentServices(tool_catalog=tool_catalog)

    def __call__(self, state: AgentRunState) -> dict[str, Any]:
        pending = state.next_pending_subgoal()
        scopes = frozenset(
            scope
            for tool in self.tool_catalog.project_tools
            for scope in tool.scopes
        )
        deps = AgentDeps(
            run_id=f"{state.run_id}:planner:{len(state.decisions)}",
            conversation_id=state.conversation_id,
            settings=self.settings,
            subject=AgentSubject(
                metadata={
                    "workflow_kind": state.workflow_kind,
                    "pending_subgoal_id": (
                        pending.subgoal_id if pending is not None else None
                    ),
                }
            ),
            permissions=AgentPermissions(tool_scopes=scopes),
            budget=state.budget,
            services=self.services,
        )
        prompt = json.dumps(
            {
                "user_goal": state.user_goal,
                "workflow_kind": state.workflow_kind,
                "pending_subgoal": (
                    pending.model_dump(mode="json") if pending else None
                ),
                "accepted_evidence_ids": state.accepted_evidence_ids,
                "available_tool_scopes": sorted(scopes),
                "available_tools": self.tool_catalog.names,
            },
            ensure_ascii=False,
        )
        result = self.agent.run_sync(prompt, deps=deps, run_id=deps.run_id)
        usage = result.usage
        usage_payload = (
            dataclasses.asdict(usage)
            if dataclasses.is_dataclass(usage)
            else dict(vars(usage))
        )
        state.trace.append(
            AgentRunTrace(
                event_type="pydantic_ai_planner",
                message="Typed planner decision validated.",
                metadata={"usage": usage_payload},
            )
        )
        recorder = self.services.message_recorder
        if recorder is not None:
            run_awaitable_sync(
                recorder.record_result(
                    run_id=deps.run_id,
                    conversation_id=state.conversation_id or state.run_id,
                    agent_name=self.agent.name or "typed_agent_planner",
                    result=result,
                )
            )
        return result.output.model_dump(mode="json")


__all__ = ["PydanticAIPlanner"]
