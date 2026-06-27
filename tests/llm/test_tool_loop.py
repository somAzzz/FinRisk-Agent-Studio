import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.llm.tool_loop import OpenAICompatibleToolLoop, ToolLoopError


def _tool_call(name: str, arguments: dict | str = "{}") -> SimpleNamespace:
    raw_args = json.dumps(arguments) if isinstance(arguments, dict) else arguments
    return SimpleNamespace(
        id="call-1",
        type="function",
        function=SimpleNamespace(name=name, arguments=raw_args),
    )


def _response(content: str, tool_calls=None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=tool_calls)
            )
        ],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
    )


def test_tool_loop_executes_registered_tool_and_finishes() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = [
        _response("", [_tool_call("lookup_metric", {"ticker": "AAPL"})]),
        _response("AAPL: 0.46", None),
    ]
    calls: list[dict] = []

    def lookup_metric(ticker: str) -> dict:
        calls.append({"ticker": ticker})
        return {"ticker": ticker, "gross_margin": 0.46}

    loop = OpenAICompatibleToolLoop(
        client=sdk,
        model="local-model",
        provider="local",
        temperature=0.1,
        max_tokens=256,
    )
    text, audit = loop.chat(
        [{"role": "user", "content": "Find margin."}],
        tools=[{"type": "function", "function": {"name": "lookup_metric"}}],
        tool_map={"lookup_metric": lookup_metric},
        tool_choice={"type": "function", "function": {"name": "lookup_metric"}},
    )

    assert text == "AAPL: 0.46"
    assert calls == [{"ticker": "AAPL"}]
    assert len(audit) == 2
    first_kwargs = sdk.chat.completions.create.call_args_list[0].kwargs
    second_kwargs = sdk.chat.completions.create.call_args_list[1].kwargs
    assert first_kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "lookup_metric"},
    }
    assert second_kwargs["tool_choice"] == "auto"
    assert second_kwargs["messages"][-1]["role"] == "tool"
    assert '"gross_margin": 0.46' in second_kwargs["messages"][-1]["content"]


def test_tool_loop_unknown_tool_is_returned_to_model_without_execution() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = [
        _response("", [_tool_call("delete_everything", {})]),
        _response("I cannot run that.", None),
    ]
    executed = False

    def safe_tool() -> str:
        nonlocal executed
        executed = True
        return "ok"

    loop = OpenAICompatibleToolLoop(
        client=sdk,
        model="local-model",
        provider="local",
        temperature=0.1,
        max_tokens=256,
    )
    text, _audit = loop.chat(
        [{"role": "user", "content": "Run bad tool."}],
        tools=[{"type": "function", "function": {"name": "safe_tool"}}],
        tool_map={"safe_tool": safe_tool},
    )

    assert text == "I cannot run that."
    assert executed is False
    second_messages = sdk.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert "unknown tool: delete_everything" in second_messages[-1]["content"]


def test_tool_loop_raises_after_max_rounds() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = [
        _response("", [_tool_call("safe_tool", {})]),
        _response("", [_tool_call("safe_tool", {})]),
    ]
    loop = OpenAICompatibleToolLoop(
        client=sdk,
        model="local-model",
        provider="local",
        temperature=0.1,
        max_tokens=256,
    )

    with pytest.raises(ToolLoopError):
        loop.chat(
            [{"role": "user", "content": "Loop."}],
            tools=[{"type": "function", "function": {"name": "safe_tool"}}],
            tool_map={"safe_tool": lambda: "ok"},
            max_tool_rounds=1,
        )
