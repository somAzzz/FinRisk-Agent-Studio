"""Typed dependencies shared by Pydantic AI agents."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.agents.state import AgentBudget
from src.config import Settings
from src.schemas.tool_trace import ToolExecutionEvent
from src.tools.contracts import ProjectTool, ToolCatalog
from src.tools.search_router import SearchRouter


class EvidenceSink(Protocol):
    """Minimal boundary for recording normalized evidence."""

    def record(self, item: object) -> object:
        """Persist or collect one evidence item."""
        ...


class TraceSink(Protocol):
    """Minimal boundary for emitting auditable runtime events."""

    def emit(self, event: Mapping[str, Any]) -> object:
        """Record one trace event."""
        ...


class AgentMessageRecorder(Protocol):
    """Persistence boundary used after a successful Agent run."""

    async def record_result(
        self,
        *,
        run_id: str,
        conversation_id: str,
        agent_name: str,
        result: object,
    ) -> object:
        """Append new messages and usage idempotently."""
        ...

    async def message_history(self, conversation_id: str) -> list[object]:
        """Load trusted server-side messages for continuation."""
        ...


@dataclass(frozen=True, slots=True)
class AgentSubject:
    """Entity or product being investigated in one Agent run."""

    ticker: str | None = None
    company_name: str | None = None
    product_name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentPermissions:
    """Per-run tool visibility and side-effect permissions."""

    tool_scopes: frozenset[str] = field(
        default_factory=lambda: frozenset({"company_research"})
    )
    allow_interactive: bool = False
    allow_write: bool = False

    def allows(self, tool: ProjectTool) -> bool:
        """Return whether a project tool is visible to this run."""
        if not self.tool_scopes.intersection(tool.scopes):
            return False
        if tool.risk_level == "interactive" and not self.allow_interactive:
            return False
        return tool.risk_level != "write_gated" or self.allow_write


@dataclass(slots=True)
class AgentServices:
    """Project services that Agents may use without relying on globals."""

    search_router: SearchRouter | None = None
    tool_catalog: ToolCatalog | None = None
    evidence_sink: EvidenceSink | None = None
    trace_sink: TraceSink | None = None
    tool_events: list[ToolExecutionEvent] = field(default_factory=list)
    message_recorder: AgentMessageRecorder | None = None


@dataclass(slots=True)
class AgentDeps:
    """Complete typed dependency object passed to Pydantic AI runs."""

    run_id: str
    settings: Settings
    conversation_id: str | None = None
    load_message_history: bool = False
    subject: AgentSubject = field(default_factory=AgentSubject)
    permissions: AgentPermissions = field(default_factory=AgentPermissions)
    budget: AgentBudget = field(default_factory=AgentBudget)
    services: AgentServices = field(default_factory=AgentServices)

    def visible_tool_catalog(self) -> ToolCatalog:
        """Filter the injected catalog through the run's permission contract."""
        catalog = self.services.tool_catalog
        if catalog is None:
            return ToolCatalog(project_tools=())
        return ToolCatalog(
            project_tools=tuple(
                tool
                for tool in catalog.project_tools
                if self.permissions.allows(tool)
            )
        )


__all__ = [
    "AgentDeps",
    "AgentMessageRecorder",
    "AgentPermissions",
    "AgentServices",
    "AgentSubject",
    "EvidenceSink",
    "TraceSink",
]
