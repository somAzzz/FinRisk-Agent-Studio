"""LLM-driven agent runtime backed by OpenAI-compatible tool calling."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.llm.tool_loop import ToolFunction
from src.schemas.finrisk import LLMCall
from src.tools.catalog import ToolCatalog, build_project_tool_catalog

DEFAULT_SYSTEM_PROMPT = """You are a financial research agent.
Use tools when you need current web evidence or page content.
Prefer web_search for discovery, web_fetch for specific URLs, and
search_and_fetch when snippets are insufficient. Do not make investment
recommendations. Distinguish evidence, inference, and uncertainty."""


class ToolCallingClient(Protocol):
    """Protocol implemented by DeepSeekClient and EdgarLLMClient."""

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        tool_map: dict[str, ToolFunction],
        max_tool_rounds: int = 4,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        extra_body: dict[str, Any] | None = None,
    ) -> tuple[str, list[LLMCall]]:
        """Run an OpenAI-compatible tool loop."""


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
    llm_calls: list[LLMCall] = Field(default_factory=list)


class LLMToolAgentRuntime:
    """Run a single LLM-driven tool-calling research loop."""

    def __init__(
        self,
        *,
        llm_client: ToolCallingClient,
        tool_catalog: ToolCatalog | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_tool_rounds: int = 4,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.tool_catalog = tool_catalog or build_project_tool_catalog()
        self.system_prompt = system_prompt
        self.max_tool_rounds = max_tool_rounds
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.tool_choice = tool_choice
        self.extra_body = extra_body

    def run(self, goal: str) -> LLMToolRunResult:
        """Execute ``goal`` with LLM-selected tools."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": goal},
        ]
        final_answer, llm_calls = self.llm_client.chat_with_tools(
            messages,
            tools=self.tool_catalog.tools,
            tool_map=self.tool_catalog.tool_map,
            max_tool_rounds=self.max_tool_rounds,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            tool_choice=self.tool_choice,
            extra_body=self.extra_body,
        )
        return LLMToolRunResult(
            goal=goal,
            final_answer=final_answer,
            tool_calls=_extract_tool_call_records(llm_calls),
            llm_calls=llm_calls,
        )


def _extract_tool_call_records(llm_calls: list[LLMCall]) -> list[LLMToolCallRecord]:
    records: list[LLMToolCallRecord] = []
    for call in llm_calls:
        structured = call.response_structured or {}
        for tool_call in structured.get("tool_calls", []):
            function = tool_call.get("function", {})
            name = function.get("name", "")
            if not name:
                continue
            records.append(
                LLMToolCallRecord(
                    round_id=call.chunk_id,
                    tool_name=name,
                    arguments=function.get("arguments", "{}"),
                )
            )
    return records


__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "LLMToolAgentRuntime",
    "LLMToolCallRecord",
    "LLMToolRunResult",
    "ToolCallingClient",
]
