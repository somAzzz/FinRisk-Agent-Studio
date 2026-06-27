"""Contracts for LLM-visible project tools."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

ToolRiskLevel = Literal["read_only", "interactive", "write_gated"]
EvidenceKind = Literal[
    "web",
    "filing",
    "transcript",
    "financial_metric",
    "graph_path",
    "browser",
    "none",
]

ToolSchema = dict[str, Any]
ToolCallable = Callable[..., Any]
ToolMap = dict[str, ToolCallable]


@dataclass(frozen=True)
class ProjectTool:
    """One LLM-visible tool plus execution and governance metadata."""

    name: str
    description: str
    parameters: dict[str, Any]
    callable: ToolCallable
    risk_level: ToolRiskLevel = "read_only"
    scopes: frozenset[str] = field(default_factory=lambda: frozenset({"default"}))
    max_result_chars: int = 12000
    evidence_kind: EvidenceKind = "none"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ProjectTool.name must be non-empty")
        if self.risk_level == "write_gated" and "default" in self.scopes:
            raise ValueError("write_gated tools must not be in the default scope")

    @property
    def openai_schema(self) -> ToolSchema:
        """Return the OpenAI-compatible function schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def executable(self) -> ToolCallable:
        """Return a callable that wraps results in a stable JSON envelope."""

        def _wrapped(**kwargs: Any) -> dict[str, Any]:
            raw = self.callable(**kwargs)
            data = jsonable(raw)
            data, truncated = truncate_jsonable(data, self.max_result_chars)
            return {
                "tool": self.name,
                "status": "success",
                "data": data,
                "evidence_kind": self.evidence_kind,
                "warnings": [],
                "truncated": truncated,
            }

        return _wrapped


@dataclass(frozen=True)
class ToolCatalog:
    """A scoped set of project tools exposed to an LLM runtime."""

    project_tools: tuple[ProjectTool, ...]

    @property
    def tools(self) -> list[ToolSchema]:
        """Return OpenAI-compatible schemas."""
        return [tool.openai_schema for tool in self.project_tools]

    @property
    def openai_tools(self) -> list[ToolSchema]:
        """Alias for callers that prefer explicit naming."""
        return self.tools

    @property
    def tool_map(self) -> ToolMap:
        """Return executable functions keyed by tool name."""
        return {tool.name: tool.executable() for tool in self.project_tools}

    @property
    def names(self) -> list[str]:
        """Return tool names in catalog order."""
        return [tool.name for tool in self.project_tools]

    def select(self, names: list[str] | tuple[str, ...]) -> ToolCatalog:
        """Return a catalog containing only the requested tool names."""
        allowed = set(names)
        return ToolCatalog(
            project_tools=tuple(
                tool for tool in self.project_tools if tool.name in allowed
            )
        )

    def for_scope(self, scope: str) -> ToolCatalog:
        """Return a catalog containing tools visible in ``scope``."""
        return ToolCatalog(
            project_tools=tuple(
                tool for tool in self.project_tools if scope in tool.scopes
            )
        )

    def without_risk_level(self, risk_level: ToolRiskLevel) -> ToolCatalog:
        """Return a catalog excluding tools with the requested risk level."""
        return ToolCatalog(
            project_tools=tuple(
                tool for tool in self.project_tools
                if tool.risk_level != risk_level
            )
        )


def jsonable(value: Any) -> Any:
    """Convert common project objects to JSON-serializable values."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return {
            key: jsonable(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return value


def truncate_jsonable(value: Any, max_chars: int) -> tuple[Any, bool]:
    """Trim a JSON-serializable value if its serialized form is too large."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return value, False
    return {
        "truncated_text": text[:max_chars],
        "original_chars": len(text),
    }, True


__all__ = [
    "EvidenceKind",
    "ProjectTool",
    "ToolCallable",
    "ToolCatalog",
    "ToolMap",
    "ToolRiskLevel",
    "ToolSchema",
    "jsonable",
    "truncate_jsonable",
]
