"""Compatibility adapter exposing a Pydantic AI Agent as SubgoalRuntime."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, UsageLimits
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models import Model

from src.agents.llm_runtime import LLMToolCallRecord, LLMToolRunResult
from src.ai.deps import AgentDeps
from src.ai.toolsets import build_scoped_toolset
from src.schemas.tool_trace import ToolBudgetUsage


class PydanticAIRuntimeAdapter:
    """Execute one research subgoal without changing GlobalAgentRuntime."""

    def __init__(
        self,
        *,
        model: Model,
        deps: AgentDeps,
        system_prompt: str,
        max_tool_result_chars: int = 12000,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        catalog = deps.services.tool_catalog
        if catalog is None:
            raise ValueError("AgentDeps.services.tool_catalog is required")
        self.deps = deps
        self.max_tool_result_chars = max_tool_result_chars
        model_settings: dict[str, Any] = {}
        if temperature is not None:
            model_settings["temperature"] = temperature
        if max_tokens is not None:
            model_settings["max_tokens"] = max_tokens
        self.agent: Agent[AgentDeps, Any] = Agent(
            model,
            output_type=str,
            deps_type=AgentDeps,
            instructions=system_prompt,
            toolsets=[build_scoped_toolset(catalog)],
            model_settings=model_settings or None,
            name="finrisk_pydantic_ai_subgoal",
        )

    @classmethod
    def from_agent(
        cls,
        *,
        agent: Agent[AgentDeps, Any],
        deps: AgentDeps,
        max_tool_result_chars: int = 12000,
    ) -> PydanticAIRuntimeAdapter:
        """Wrap a domain-specific typed Agent in the legacy runtime contract."""
        instance = cls.__new__(cls)
        instance.agent = agent
        instance.deps = deps
        instance.max_tool_result_chars = max_tool_result_chars
        return instance

    def run(self, goal: str) -> LLMToolRunResult:
        """Run the async Pydantic AI loop behind the legacy sync protocol."""
        self.deps.services.tool_events.clear()
        limits = UsageLimits(
            request_limit=max(
                1, self.deps.budget.max_tool_rounds_per_subgoal + 1
            ),
            tool_calls_limit=self.deps.budget.max_total_tool_calls,
        )
        result = run_awaitable_sync(
            self._run_and_record(
                goal,
                limits=limits,
            )
        )
        tool_calls = [
            LLMToolCallRecord(
                round_id=None,
                tool_name=part.tool_name,
                arguments=part.args_as_json_str(),
            )
            for message in result.all_messages()
            for part in message.parts
            if isinstance(part, ToolCallPart)
        ]
        events = list(self.deps.services.tool_events)
        used_chars = sum(event.result_chars for event in events)
        output = result.output
        if isinstance(output, BaseModel):
            final_answer = json.dumps(
                output.model_dump(mode="json"), ensure_ascii=False
            )
        else:
            final_answer = str(output)
        return LLMToolRunResult(
            goal=goal,
            final_answer=final_answer,
            tool_calls=tool_calls,
            tool_events=events,
            llm_calls=[],
            budget_usage=ToolBudgetUsage(
                max_tool_result_chars=self.max_tool_result_chars,
                max_total_tool_result_chars=(
                    self.deps.budget.max_total_tool_result_chars
                ),
                used_tool_result_chars=used_chars,
                truncated_events=sum(event.truncated for event in events),
            ),
            mode="native",
        )

    async def _run_and_record(self, goal: str, *, limits: UsageLimits) -> Any:
        conversation_id = self.deps.conversation_id or self.deps.run_id
        recorder = self.deps.services.message_recorder
        message_history = None
        if recorder is not None and self.deps.load_message_history:
            message_history = await recorder.message_history(conversation_id)
        result = await self.agent.run(
            goal,
            deps=self.deps,
            message_history=message_history,
            usage_limits=limits,
            run_id=self.deps.run_id,
            conversation_id=conversation_id,
        )
        if recorder is not None:
            await recorder.record_result(
                run_id=self.deps.run_id,
                conversation_id=conversation_id,
                agent_name=self.agent.name or "unnamed_agent",
                result=result,
            )
        return result


def run_awaitable_sync(awaitable: Any) -> Any:
    """Resolve an awaitable from synchronous workflow code."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    outcome: dict[str, Any] = {}

    def runner() -> None:
        try:
            outcome["value"] = asyncio.run(awaitable)
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=runner, name="pydantic-ai-subgoal")
    thread.start()
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


__all__ = ["PydanticAIRuntimeAdapter", "run_awaitable_sync"]
