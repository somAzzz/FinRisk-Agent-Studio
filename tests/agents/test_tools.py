"""Tests for the Tool protocol and ToolRegistry."""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.tools import Tool, ToolRegistry, ToolResult


class EchoTool:
    name = "echo"

    def call(self, **kwargs: Any) -> dict[str, Any]:
        return {"echo": kwargs}


class FlakyTool:
    name = "flaky"

    def call(self, **kwargs: Any) -> dict[str, Any]:  # pragma: no cover - raised
        raise ValueError("explode")


def test_registry_registers_and_calls_tool() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    result = registry.call("echo", x=1, y="z")
    assert isinstance(result, ToolResult)
    assert result.tool_name == "echo"
    assert result.success is True
    assert result.error is None
    assert result.content == {"echo": {"x": 1, "y": "z"}}


def test_registry_catches_exceptions() -> None:
    registry = ToolRegistry()
    registry.register(FlakyTool())
    result = registry.call("flaky")
    assert result.success is False
    assert result.error is not None
    assert "explode" in result.error
    assert "ValueError" in result.error


def test_registry_unknown_tool_returns_failed_result() -> None:
    registry = ToolRegistry()
    result = registry.call("nope")
    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "unknown tool" in (result.error or "")


def test_registry_rejects_tool_with_empty_name() -> None:
    class Nameless:
        name = ""

        def call(self, **kwargs: Any) -> dict[str, Any]:
            return {}

    registry = ToolRegistry()
    with pytest.raises(ValueError):
        registry.register(Nameless())  # type: ignore[arg-type]


def test_registry_has() -> None:
    registry = ToolRegistry()
    assert registry.has("echo") is False
    registry.register(EchoTool())
    assert registry.has("echo") is True


def test_tool_protocol_satisfied() -> None:
    # Structural check: a class implementing name + call satisfies Tool.
    assert isinstance(EchoTool(), Tool)
