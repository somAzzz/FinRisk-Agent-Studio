"""Provider-neutral tool-calling loop for OpenAI-compatible chat APIs."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from src.schemas.finrisk import LLMCall
from src.schemas.tool_trace import ToolBudgetUsage, ToolExecutionEvent, ToolLoopMode

ToolFunction = Callable[..., Any]
NoOpSink = Callable[[LLMCall], None]
DEFAULT_MAX_TOOL_RESULT_CHARS = 12000
DEFAULT_MAX_TOTAL_TOOL_RESULT_CHARS = 40000
TOOL_EVENT_RESULT_SUMMARY_CHARS = 4000


class ToolLoopError(Exception):
    """Raised when an OpenAI-compatible tool loop cannot complete."""


class OpenAICompatibleToolLoop:
    """Execute model-requested tools for an OpenAI-compatible SDK client.

    The model can only request tool calls. This loop is the application-side
    executor that runs local functions, appends ``role="tool"`` messages, and
    calls the model again until it returns a final assistant message.
    """

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        provider: str,
        temperature: float,
        max_tokens: int,
        llm_call_sink: NoOpSink | None = None,
        step_name: str = "llm_tool_calling",
        mode: ToolLoopMode = "native",
        max_tool_result_chars: int = DEFAULT_MAX_TOOL_RESULT_CHARS,
        max_total_tool_result_chars: int = DEFAULT_MAX_TOTAL_TOOL_RESULT_CHARS,
    ) -> None:
        self.client = client
        self.model = model
        self.provider = provider
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._llm_call_sink: NoOpSink = llm_call_sink or (lambda _call: None)
        self.step_name = step_name
        self.mode: ToolLoopMode = mode
        self.max_tool_result_chars = max_tool_result_chars
        self.max_total_tool_result_chars = max_total_tool_result_chars
        self.last_tool_events: list[ToolExecutionEvent] = []
        self.last_budget_usage = ToolBudgetUsage(
            max_tool_result_chars=max_tool_result_chars,
            max_total_tool_result_chars=max_total_tool_result_chars,
        )

    def complete(
        self,
        prompt: str,
        *,
        tools: list[dict[str, Any]],
        tool_map: Mapping[str, ToolFunction],
        system: str | None = None,
        max_tool_rounds: int = 4,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        extra_body: dict[str, Any] | None = None,
        max_tool_result_chars: int | None = None,
        max_total_tool_result_chars: int | None = None,
    ) -> str:
        """Run a prompt through the tool loop and return the final text."""
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        content, _calls = self.chat(
            messages,
            tools=tools,
            tool_map=tool_map,
            max_tool_rounds=max_tool_rounds,
            max_tokens=max_tokens,
            temperature=temperature,
            tool_choice=tool_choice,
            extra_body=extra_body,
            max_tool_result_chars=max_tool_result_chars,
            max_total_tool_result_chars=max_total_tool_result_chars,
        )
        return content

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        tool_map: Mapping[str, ToolFunction],
        max_tool_rounds: int = 4,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        extra_body: dict[str, Any] | None = None,
        max_tool_result_chars: int | None = None,
        max_total_tool_result_chars: int | None = None,
    ) -> tuple[str, list[LLMCall]]:
        """Return ``(final_text, audit_calls)`` after resolving tool calls."""
        if not tools:
            raise ValueError("tools must contain at least one tool schema")
        if not tool_map:
            raise ValueError("tool_map must contain executable functions")

        transcript = [dict(message) for message in messages]
        audit_calls: list[LLMCall] = []
        self.last_tool_events = []
        per_tool_limit = (
            self.max_tool_result_chars
            if max_tool_result_chars is None else max_tool_result_chars
        )
        total_limit = (
            self.max_total_tool_result_chars
            if max_total_tool_result_chars is None else max_total_tool_result_chars
        )
        self.last_budget_usage = ToolBudgetUsage(
            max_tool_result_chars=max(0, per_tool_limit),
            max_total_tool_result_chars=max(0, total_limit),
        )
        for round_index in range(max_tool_rounds + 1):
            request_tool_choice = tool_choice if round_index == 0 else "auto"
            started = datetime.now(tz=UTC)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=deepcopy(transcript),
                tools=tools,
                tool_choice=request_tool_choice,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                **({"extra_body": extra_body} if extra_body is not None else {}),
            )
            message = response.choices[0].message
            completed = datetime.now(tz=UTC)
            tool_calls = list(_field(message, "tool_calls", None) or [])
            content = _field(message, "content", None) or ""
            audit = self._build_audit_call(
                messages=transcript,
                content=content,
                tool_calls=tool_calls,
                started=started,
                completed=completed,
                round_index=round_index,
                usage=getattr(response, "usage", None),
            )
            audit_calls.append(audit)
            self._llm_call_sink(audit)

            transcript.append(assistant_message_to_dict(message))
            if not tool_calls:
                return content, audit_calls

            for tool_call in tool_calls:
                remaining_budget = max(
                    0,
                    self.last_budget_usage.max_total_tool_result_chars
                    - self.last_budget_usage.used_tool_result_chars,
                )
                tool_message_row, event = execute_tool_call_with_event(
                    tool_call,
                    tool_map,
                    round_id=f"round-{round_index}",
                    max_result_chars=min(
                        self.last_budget_usage.max_tool_result_chars,
                        remaining_budget,
                    ),
                )
                self.last_tool_events.append(event)
                used_chars = len(tool_message_row.get("content", ""))
                self.last_budget_usage.used_tool_result_chars += used_chars
                if event.truncated:
                    self.last_budget_usage.truncated_events += 1
                transcript.append(tool_message_row)

        raise ToolLoopError(
            f"tool-calling loop exceeded max_tool_rounds={max_tool_rounds}"
        )

    def _build_audit_call(
        self,
        *,
        messages: list[dict[str, Any]],
        content: str,
        tool_calls: list[Any],
        started: datetime,
        completed: datetime,
        round_index: int,
        usage: Any | None,
    ) -> LLMCall:
        latency_ms = int((completed - started).total_seconds() * 1000)
        return LLMCall(
            call_id=f"tool-{uuid.uuid4().hex[:12]}",
            step_name=self.step_name,
            chunk_id=f"round-{round_index}",
            provider=self.provider,
            model=self.model,
            messages=messages,
            prompt_text=messages[-1].get("content", "") if messages else "",
            response_text=content,
            response_structured={
                "tool_calls": [tool_call_to_dict(tc) for tc in tool_calls]
            },
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", None) if usage else None,
            latency_ms=latency_ms,
            started_at=started,
            completed_at=completed,
        )


def assistant_message_to_dict(message: Any) -> dict[str, Any]:
    """Project an OpenAI SDK assistant message into a serializable dict."""
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": _field(message, "content", None) or "",
    }
    tool_calls = list(_field(message, "tool_calls", None) or [])
    if tool_calls:
        payload["tool_calls"] = [tool_call_to_dict(tc) for tc in tool_calls]
    return payload


def tool_call_to_dict(tool_call: Any) -> dict[str, Any]:
    """Return the API wire shape for a function tool call."""
    function = _field(tool_call, "function", {})
    return {
        "id": _field(tool_call, "id", ""),
        "type": _field(tool_call, "type", "function"),
        "function": {
            "name": _field(function, "name", ""),
            "arguments": _field(function, "arguments", "{}"),
        },
    }


def execute_tool_call(
    tool_call: Any,
    tool_map: Mapping[str, ToolFunction],
) -> dict[str, Any]:
    """Execute one model-requested tool call and return a ``role=tool`` row."""
    message, _event = execute_tool_call_with_event(
        tool_call,
        tool_map,
        round_id="round-unknown",
        max_result_chars=DEFAULT_MAX_TOOL_RESULT_CHARS,
    )
    return message


def execute_tool_call_with_event(
    tool_call: Any,
    tool_map: Mapping[str, ToolFunction],
    *,
    round_id: str,
    max_result_chars: int = DEFAULT_MAX_TOOL_RESULT_CHARS,
) -> tuple[dict[str, Any], ToolExecutionEvent]:
    """Execute a tool call and return both model message and backend event."""
    started = datetime.now(tz=UTC)
    function = _field(tool_call, "function", {})
    name = _field(function, "name", "")
    raw_args = _field(function, "arguments", "{}") or "{}"
    tool_call_id = _field(tool_call, "id", "")
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError as exc:
        result = {"error": f"invalid JSON arguments: {exc.msg}"}
        message = tool_message(tool_call, result, max_result_chars=max_result_chars)
        return message, _tool_event(
            started=started,
            round_id=round_id,
            tool_call_id=tool_call_id,
            tool_name=name,
            arguments={},
            status="failed",
            content=message["content"],
            error=result["error"],
        )
    if not isinstance(args, dict):
        result = {"error": "tool arguments must be an object"}
        message = tool_message(tool_call, result, max_result_chars=max_result_chars)
        return message, _tool_event(
            started=started,
            round_id=round_id,
            tool_call_id=tool_call_id,
            tool_name=name,
            arguments={},
            status="failed",
            content=message["content"],
            error=result["error"],
        )
    tool = tool_map.get(name)
    if tool is None:
        result = {"error": f"unknown tool: {name}"}
        message = tool_message(tool_call, result, max_result_chars=max_result_chars)
        return message, _tool_event(
            started=started,
            round_id=round_id,
            tool_call_id=tool_call_id,
            tool_name=name,
            arguments=args,
            status="failed",
            content=message["content"],
            error=result["error"],
        )
    try:
        result = tool(**args)
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
        message = tool_message(tool_call, result, max_result_chars=max_result_chars)
        return message, _tool_event(
            started=started,
            round_id=round_id,
            tool_call_id=tool_call_id,
            tool_name=name,
            arguments=args,
            status="failed",
            content=message["content"],
            error=result["error"],
        )
    message = tool_message(tool_call, result, max_result_chars=max_result_chars)
    return message, _tool_event(
        started=started,
        round_id=round_id,
        tool_call_id=tool_call_id,
        tool_name=name,
        arguments=args,
        status="success",
        content=message["content"],
        error=None,
    )


def tool_message(
    tool_call: Any,
    result: Any,
    *,
    max_result_chars: int = DEFAULT_MAX_TOOL_RESULT_CHARS,
) -> dict[str, Any]:
    """Serialize a local tool result for the next model round."""
    if isinstance(result, str):
        content = result
    else:
        content = json.dumps(result, ensure_ascii=False, default=str)
    content = _truncate_content(content, max_result_chars)
    return {
        "role": "tool",
        "tool_call_id": _field(tool_call, "id", ""),
        "content": content,
    }


def _tool_event(
    *,
    started: datetime,
    round_id: str,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    status: str,
    content: str,
    error: str | None,
) -> ToolExecutionEvent:
    completed = datetime.now(tz=UTC)
    latency_ms = int((completed - started).total_seconds() * 1000)
    return ToolExecutionEvent(
        event_id=f"tool-event-{uuid.uuid4().hex[:12]}",
        round_id=round_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        arguments=arguments,
        status=status,  # type: ignore[arg-type]
        result_summary=content[:TOOL_EVENT_RESULT_SUMMARY_CHARS],
        latency_ms=latency_ms,
        error=error,
        result_chars=len(content),
        truncated='"truncated": true' in content or '"truncated_text"' in content,
        created_at=completed,
    )


def _truncate_content(content: str, max_chars: int) -> str:
    if max_chars <= 0:
        return json.dumps(
            {
                "truncated": True,
                "truncated_text": "",
                "original_chars": len(content),
            },
            ensure_ascii=False,
        )
    if len(content) <= max_chars:
        return content
    return json.dumps(
        {
            "truncated": True,
            "truncated_text": content[:max_chars],
            "original_chars": len(content),
        },
        ensure_ascii=False,
    )


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


__all__ = [
    "DEFAULT_MAX_TOOL_RESULT_CHARS",
    "DEFAULT_MAX_TOTAL_TOOL_RESULT_CHARS",
    "NoOpSink",
    "OpenAICompatibleToolLoop",
    "ToolFunction",
    "ToolLoopError",
    "assistant_message_to_dict",
    "execute_tool_call",
    "execute_tool_call_with_event",
    "tool_call_to_dict",
    "tool_message",
]
