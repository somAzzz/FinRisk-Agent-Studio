"""Tool protocol and a small registry that wraps tool calls safely."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.evidence import Evidence


class ToolResult(BaseModel):
    """The outcome of a tool invocation."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    success: bool
    content: Any = None
    error: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


@runtime_checkable
class Tool(Protocol):
    """A callable unit of work that the runtime can dispatch to."""

    name: str

    def call(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the tool and return a JSON-serializable result dict."""
        ...


class ToolRegistry:
    """In-memory registry of named tools.

    The registry is responsible for catching exceptions raised by tools and
    converting them into :class:`ToolResult` instances with ``success=False``
    so the runtime can record them in ``tool_history`` without crashing.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool under its ``name`` attribute."""
        if not tool.name:
            msg = "Tool.name must be a non-empty string."
            raise ValueError(msg)
        self._tools[tool.name] = tool

    def has(self, name: str) -> bool:
        """Return True if a tool with the given name is registered."""
        return name in self._tools

    def __contains__(self, name: str) -> bool:
        """Support ``name in registry`` syntax."""
        return self.has(name)

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        """Invoke a registered tool, returning a :class:`ToolResult`.

        Unknown tools and tool exceptions both surface as
        :class:`ToolResult` instances with ``success=False`` so callers do
        not need to wrap calls in try/except.
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_name=name,
                success=False,
                error=f"unknown tool: {name}",
            )
        try:
            content = tool.call(**kwargs)
        except Exception as exc:  # noqa: BLE001 - surfaced via ToolResult
            return ToolResult(
                tool_name=name,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )
        return ToolResult(tool_name=name, success=True, content=content)
