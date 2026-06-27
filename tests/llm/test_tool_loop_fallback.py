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
