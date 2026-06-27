"""JSON tool-choice fallback tests for local OpenAI-compatible models."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.llm.client import EdgarLLMClient
from src.llm.tool_loop import JSONToolChoiceToolLoop


def _response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
    )


def test_json_tool_choice_loop_executes_tool_and_finishes() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = [
        _response(json.dumps({"tool": "lookup_metric", "arguments": {"ticker": "AAPL"}})),
        _response(json.dumps({"final_answer": "AAPL gross margin is 46%."})),
    ]

    loop = JSONToolChoiceToolLoop(
        client=sdk,
        model="local-model",
        provider="local",
        temperature=0.1,
        max_tokens=256,
    )
    text, calls = loop.chat(
        [{"role": "user", "content": "Find AAPL margin."}],
        tools=[{"type": "function", "function": {"name": "lookup_metric"}}],
        tool_map={"lookup_metric": lambda ticker: {"ticker": ticker, "value": 0.46}},
    )

    assert text == "AAPL gross margin is 46%."
    assert len(calls) == 2
    assert loop.mode == "json_fallback"
    assert loop.last_tool_events[0].tool_name == "lookup_metric"
    assert loop.last_tool_events[0].arguments == {"ticker": "AAPL"}
    first_kwargs = sdk.chat.completions.create.call_args_list[0].kwargs
    second_kwargs = sdk.chat.completions.create.call_args_list[1].kwargs
    assert "tools" not in first_kwargs
    assert "tools" not in second_kwargs
    assert "Tool result for lookup_metric" in second_kwargs["messages"][-1]["content"]


def test_json_tool_choice_loop_finalizes_after_max_rounds() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = [
        _response(json.dumps({"tool": "lookup_metric", "arguments": {"ticker": "AAPL"}})),
        _response(json.dumps({"tool": "lookup_metric", "arguments": {"ticker": "MSFT"}})),
        _response(json.dumps({"final_answer": "Final answer from available evidence."})),
    ]
    loop = JSONToolChoiceToolLoop(
        client=sdk,
        model="local-model",
        provider="local",
        temperature=0.1,
        max_tokens=256,
    )

    text, calls = loop.chat(
        [{"role": "user", "content": "Keep looking up metrics."}],
        tools=[{"type": "function", "function": {"name": "lookup_metric"}}],
        tool_map={"lookup_metric": lambda ticker: {"ticker": ticker}},
        max_tool_rounds=1,
    )

    assert text == "Final answer from available evidence."
    assert len(calls) == 3
    assert len(loop.last_tool_events) == 2
    final_kwargs = sdk.chat.completions.create.call_args_list[2].kwargs
    assert "tools" not in final_kwargs
    assert "Tool-call budget is exhausted" in final_kwargs["messages"][-1]["content"]


def test_json_tool_choice_loop_does_not_execute_after_total_budget_exhausted() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = [
        _response(json.dumps({"tool": "large_tool", "arguments": {}})),
        _response(json.dumps({"tool": "second_tool", "arguments": {}})),
        _response(json.dumps({"final_answer": "Final answer from available evidence."})),
    ]
    calls: list[str] = []

    def large_tool() -> dict:
        calls.append("large_tool")
        return "x" * 20

    def second_tool() -> dict:
        calls.append("second_tool")
        return {"text": "should not execute"}

    loop = JSONToolChoiceToolLoop(
        client=sdk,
        model="local-model",
        provider="local",
        temperature=0.1,
        max_tokens=256,
    )

    text, _calls = loop.chat(
        [{"role": "user", "content": "Use tools until done."}],
        tools=[
            {"type": "function", "function": {"name": "large_tool"}},
            {"type": "function", "function": {"name": "second_tool"}},
        ],
        tool_map={"large_tool": large_tool, "second_tool": second_tool},
        max_tool_rounds=2,
        max_tool_result_chars=20,
        max_total_tool_result_chars=20,
    )

    assert text == "Final answer from available evidence."
    assert calls == ["large_tool"]
    assert len(loop.last_tool_events) == 2
    assert loop.last_tool_events[1].status == "failed"
    assert loop.last_tool_events[1].tool_name == "second_tool"
    assert loop.last_tool_events[1].error is not None
    assert "budget exhausted" in loop.last_tool_events[1].error
    assert loop.last_budget_usage.used_tool_result_chars == 20
    final_messages = sdk.chat.completions.create.call_args_list[2].kwargs["messages"]
    assert "budget exhausted" in final_messages[-1]["content"]


def test_local_client_json_fallback_mode_uses_json_loop() -> None:
    with patch("src.llm.client.OpenAI") as OpenAIMock:
        sdk = OpenAIMock.return_value
        sdk.chat.completions.create.side_effect = [
            _response(json.dumps({"tool": "lookup_metric", "arguments": {"ticker": "AAPL"}})),
            _response(json.dumps({"final_answer": "done"})),
        ]
        client = EdgarLLMClient(
            model="local-model",
            provider="vllm",
            tool_loop_mode="json_fallback",
        )
        text = client.complete_with_tools(
            "Find margin.",
            tools=[{"type": "function", "function": {"name": "lookup_metric"}}],
            tool_map={"lookup_metric": lambda ticker: {"ticker": ticker}},
        )

    assert text == "done"
    assert client.last_tool_loop_mode == "json_fallback"
    assert client.last_tool_events[0].tool_name == "lookup_metric"


def test_local_client_auto_falls_back_when_native_tools_fail() -> None:
    with patch("src.llm.client.OpenAI") as OpenAIMock:
        sdk = OpenAIMock.return_value
        sdk.chat.completions.create.side_effect = [
            RuntimeError("tools unsupported"),
            _response(json.dumps({"tool": "lookup_metric", "arguments": {"ticker": "AAPL"}})),
            _response(json.dumps({"final_answer": "fallback done"})),
        ]
        client = EdgarLLMClient(
            model="local-model",
            provider="sglang",
            tool_loop_mode="auto",
        )
        text = client.complete_with_tools(
            "Find margin.",
            tools=[{"type": "function", "function": {"name": "lookup_metric"}}],
            tool_map={"lookup_metric": lambda ticker: {"ticker": ticker}},
        )

    assert text == "fallback done"
    assert client.last_tool_loop_mode == "json_fallback"
    assert client.last_tool_events[0].status == "success"
