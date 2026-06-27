"""Trace schemas for LLM-driven tool execution."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ToolLoopMode = Literal["native", "json_fallback", "auto"]
ToolExecutionStatus = Literal["success", "failed"]


class ToolExecutionEvent(BaseModel):
    """One backend-side execution of a model-requested tool call."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    round_id: str
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: ToolExecutionStatus
    result_summary: str = ""
    latency_ms: int = Field(ge=0)
    error: str | None = None
    result_chars: int = Field(default=0, ge=0)
    truncated: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolBudgetUsage(BaseModel):
    """Budget usage for tool results passed back to the model."""

    model_config = ConfigDict(extra="forbid")

    max_tool_result_chars: int = Field(ge=0)
    max_total_tool_result_chars: int = Field(ge=0)
    used_tool_result_chars: int = Field(default=0, ge=0)
    truncated_events: int = Field(default=0, ge=0)


class ToolLoopTrace(BaseModel):
    """Complete tool-loop trace metadata for a single run."""

    model_config = ConfigDict(extra="forbid")

    mode: ToolLoopMode = "native"
    tool_events: list[ToolExecutionEvent] = Field(default_factory=list)
    budget_usage: ToolBudgetUsage | None = None


__all__ = [
    "ToolBudgetUsage",
    "ToolExecutionEvent",
    "ToolExecutionStatus",
    "ToolLoopMode",
    "ToolLoopTrace",
]
