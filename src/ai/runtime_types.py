"""Shared runtime result types for agent subgoal execution.

These Pydantic models define the serialized contract used by the Pydantic AI
runtime and the workflow/API boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.finrisk import LLMCall
from src.schemas.tool_trace import ToolBudgetUsage, ToolExecutionEvent, ToolLoopMode

DEFAULT_SYSTEM_PROMPT = """You are a financial research agent.
Use tools when you need current web evidence or page content.
Prefer web_search for discovery, web_fetch for specific URLs, and
search_and_fetch when snippets are insufficient. Do not make investment
recommendations. Distinguish evidence, inference, and uncertainty."""


class LLMToolCallRecord(BaseModel):
    """One model-requested tool call captured from the audit log."""

    model_config = ConfigDict(extra="forbid")

    round_id: str | None = None
    tool_name: str
    arguments: str = "{}"


class LLMToolRunResult(BaseModel):
    """Final answer plus trace metadata for an LLM-driven tool run."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    final_answer: str
    tool_calls: list[LLMToolCallRecord] = Field(default_factory=list)
    tool_events: list[ToolExecutionEvent] = Field(default_factory=list)
    llm_calls: list[LLMCall] = Field(default_factory=list)
    budget_usage: ToolBudgetUsage | None = None
    mode: ToolLoopMode = "native"


__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "LLMToolCallRecord",
    "LLMToolRunResult",
]
