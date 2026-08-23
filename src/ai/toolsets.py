"""Typed Pydantic AI toolsets backed by the legacy project services."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import FunctionToolset, RunContext, Tool
from pydantic_ai.toolsets import AbstractToolset, FilteredToolset

from src.ai.deps import AgentDeps
from src.schemas.tool_trace import ToolExecutionEvent
from src.tools.contracts import ProjectTool, ToolCatalog

SearchIntent = Literal[
    "general",
    "news",
    "sec",
    "ir",
    "transcript",
    "semantic",
    "agent_research",
    "verification",
    "product_supply_chain",
    "supplier_discovery",
    "component_supplier",
    "cloud_dependency",
    "datacenter_power",
    "semiconductor_supply_chain",
    "supply_chain",
    "policy",
    "geopolitical",
]
SearchProvider = Literal["auto", "duckduckgo", "brave", "tavily"]
TimeRange = Literal["d", "w", "m", "y"] | None
FilingSection = Literal[
    "full_text",
    "1",
    "1A",
    "7",
    "7A",
    "section_1",
    "section_1a",
    "section_7",
    "section_7a",
]
TranscriptSection = Literal["all", "prepared_remarks", "qa", "unknown"]

ResultsLimit = Annotated[int, Field(ge=1, le=10)]
PageLimit = Annotated[int, Field(ge=1, le=5)]
FilingLimit = Annotated[int, Field(ge=1, le=20)]
Quarter = Annotated[int, Field(ge=1, le=4)]
OptionalQuarter = Annotated[int | None, Field(ge=1, le=4)]
HopLimit = Annotated[int, Field(ge=1, le=4)]
BrowserSteps = Annotated[int, Field(ge=1, le=10)]
BrowserTimeout = Annotated[float, Field(ge=0.1, le=120)]


class ToolResultEnvelope(BaseModel):
    """Stable result contract returned to the model by every project tool."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    status: Literal["success", "failed"]
    data: Any = None
    evidence_kind: str = "none"
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False
    error: str | None = None


async def _invoke_project_tool(
    ctx: RunContext[AgentDeps], tool_name: str, arguments: dict[str, Any]
) -> ToolResultEnvelope:
    """Execute a legacy callable asynchronously and project an audit event."""
    catalog = ctx.deps.services.tool_catalog
    project_tool = _find_tool(catalog, tool_name)
    started = time.perf_counter()
    created_at = datetime.now(UTC)
    error: str | None = None
    try:
        if project_tool is None:
            raise LookupError(f"tool {tool_name!r} is not in the injected catalog")
        if not ctx.deps.permissions.allows(project_tool):
            raise PermissionError(f"tool {tool_name!r} is not allowed for this run")
        raw = await asyncio.to_thread(project_tool.executable(), **arguments)
        envelope = ToolResultEnvelope.model_validate(raw)
    except Exception as exc:  # project tools must return an auditable failure
        error = f"{type(exc).__name__}: {exc}"
        envelope = ToolResultEnvelope(
            tool=tool_name,
            status="failed",
            evidence_kind=(
                project_tool.evidence_kind if project_tool is not None else "none"
            ),
            warnings=["tool execution failed"],
            error=error,
        )

    content = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False)
    event = ToolExecutionEvent(
        event_id=f"tool-event-{uuid.uuid4().hex[:12]}",
        round_id=f"round-{max(0, ctx.run_step - 1)}",
        tool_call_id=ctx.tool_call_id or f"tool-call-{uuid.uuid4().hex[:12]}",
        tool_name=tool_name,
        arguments=arguments,
        status=envelope.status,
        result_summary=content[:500],
        latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
        error=error,
        result_chars=len(content),
        truncated=envelope.truncated,
        created_at=created_at,
    )
    ctx.deps.services.tool_events.append(event)
    trace_sink = ctx.deps.services.trace_sink
    if trace_sink is not None:
        emitted = trace_sink.emit(event.model_dump(mode="json"))
        if inspect.isawaitable(emitted):
            await emitted
    return envelope


def _find_tool(catalog: ToolCatalog | None, name: str) -> ProjectTool | None:
    if catalog is None:
        return None
    return next((tool for tool in catalog.project_tools if tool.name == name), None)


async def web_search(
    ctx: RunContext[AgentDeps],
    query: str,
    intent: SearchIntent = "general",
    max_results: ResultsLimit = 5,
    time_range: TimeRange = None,
    provider: SearchProvider = "auto",
) -> ToolResultEnvelope:
    """Search current web sources through the project's governed router."""
    return await _invoke_project_tool(ctx, "web_search", locals_without_ctx(locals()))


async def web_fetch(
    ctx: RunContext[AgentDeps], url: str
) -> ToolResultEnvelope:
    """Fetch and extract one HTTP(S) source under SSRF controls."""
    return await _invoke_project_tool(ctx, "web_fetch", {"url": url})


async def search_and_fetch(
    ctx: RunContext[AgentDeps],
    query: str,
    intent: SearchIntent = "general",
    max_results: ResultsLimit = 5,
    max_pages: PageLimit = 3,
    time_range: TimeRange = None,
    provider: SearchProvider = "auto",
) -> ToolResultEnvelope:
    """Search and fetch the highest-ranked pages in one governed operation."""
    return await _invoke_project_tool(
        ctx, "search_and_fetch", locals_without_ctx(locals())
    )


async def sec_list_filings(
    ctx: RunContext[AgentDeps],
    ticker: str,
    form_types: list[str] | None = None,
    since: str | None = None,
    limit: FilingLimit = 5,
) -> ToolResultEnvelope:
    """List recent SEC filings for a ticker."""
    return await _invoke_project_tool(
        ctx, "sec_list_filings", locals_without_ctx(locals())
    )


async def sec_fetch_filing(
    ctx: RunContext[AgentDeps],
    ticker: str,
    accession_number: str | None = None,
    form_types: list[str] | None = None,
    section: FilingSection = "full_text",
) -> ToolResultEnvelope:
    """Fetch a governed section from a selected SEC filing."""
    return await _invoke_project_tool(
        ctx, "sec_fetch_filing", locals_without_ctx(locals())
    )


async def transcript_lookup(
    ctx: RunContext[AgentDeps],
    ticker: str,
    year: int,
    quarter: Quarter,
    section: TranscriptSection = "all",
) -> ToolResultEnvelope:
    """Load an earnings transcript and optionally select one section."""
    return await _invoke_project_tool(
        ctx, "transcript_lookup", locals_without_ctx(locals())
    )


async def management_snapshot_lookup(
    ctx: RunContext[AgentDeps],
    ticker: str,
    year: int,
    quarter: Quarter,
    compare_year: int | None = None,
    compare_quarter: OptionalQuarter = None,
) -> ToolResultEnvelope:
    """Compare management statements across two earnings periods."""
    return await _invoke_project_tool(
        ctx, "management_snapshot_lookup", locals_without_ctx(locals())
    )


async def financial_metrics_lookup(
    ctx: RunContext[AgentDeps],
    ticker: str,
    metrics: list[str] | None = None,
) -> ToolResultEnvelope:
    """Load selected financial metrics for one ticker."""
    return await _invoke_project_tool(
        ctx, "financial_metrics_lookup", locals_without_ctx(locals())
    )


async def xbrl_fact_lookup(
    ctx: RunContext[AgentDeps],
    ticker: str,
    concepts: Annotated[list[str], Field(min_length=1)],
    unit: str = "USD",
    limit: FilingLimit = 5,
) -> ToolResultEnvelope:
    """Load recent SEC XBRL facts for selected concepts."""
    return await _invoke_project_tool(
        ctx, "xbrl_fact_lookup", locals_without_ctx(locals())
    )


async def financial_snapshot_lookup(
    ctx: RunContext[AgentDeps], ticker: str, as_of: str | None = None
) -> ToolResultEnvelope:
    """Build a normalized point-in-time financial snapshot."""
    return await _invoke_project_tool(
        ctx, "financial_snapshot_lookup", locals_without_ctx(locals())
    )


async def graph_query(
    ctx: RunContext[AgentDeps],
    entity: str,
    ticker: str | None = None,
    max_hops: HopLimit = 3,
    allowed_edge_types: list[str] | None = None,
) -> ToolResultEnvelope:
    """Query governed graph paths around an entity."""
    return await _invoke_project_tool(
        ctx, "graph_query", locals_without_ctx(locals())
    )


async def graph_path_search(
    ctx: RunContext[AgentDeps],
    source_entity: str,
    target_entity: str | None = None,
    ticker: str | None = None,
    max_hops: HopLimit = 3,
    allowed_edge_types: list[str] | None = None,
) -> ToolResultEnvelope:
    """Find governed graph paths between source and optional target entities."""
    return await _invoke_project_tool(
        ctx, "graph_path_search", locals_without_ctx(locals())
    )


async def browser_explore(
    ctx: RunContext[AgentDeps],
    goal: str,
    initial_urls: list[str] | None = None,
    max_steps: BrowserSteps = 5,
    timeout_seconds: BrowserTimeout = 60,
) -> ToolResultEnvelope:
    """Explore interactive pages under explicit run permission and limits."""
    return await _invoke_project_tool(
        ctx, "browser_explore", locals_without_ctx(locals())
    )


def locals_without_ctx(values: dict[str, Any]) -> dict[str, Any]:
    """Copy function arguments while excluding the Pydantic AI context."""
    return {key: value for key, value in values.items() if key != "ctx"}


_TYPED_TOOLS = {
    function.__name__: function
    for function in (
        web_search,
        web_fetch,
        search_and_fetch,
        sec_list_filings,
        sec_fetch_filing,
        transcript_lookup,
        management_snapshot_lookup,
        financial_metrics_lookup,
        xbrl_fact_lookup,
        financial_snapshot_lookup,
        graph_query,
        graph_path_search,
        browser_explore,
    )
}


def build_project_function_toolset(catalog: ToolCatalog) -> FunctionToolset[AgentDeps]:
    """Build typed tools while preserving legacy governance metadata."""
    toolset: FunctionToolset[AgentDeps] = FunctionToolset(
        id="finrisk-project-tools",
        include_return_schema=False,
    )
    for project_tool in catalog.project_tools:
        function = _TYPED_TOOLS.get(project_tool.name)
        if function is None:
            raise ValueError(f"No typed wrapper for project tool {project_tool.name!r}")
        toolset.add_tool(
            Tool(
                function,
                name=project_tool.name,
                description=project_tool.description,
                metadata={
                    "scopes": sorted(project_tool.scopes),
                    "risk_level": project_tool.risk_level,
                    "evidence_kind": project_tool.evidence_kind,
                    "max_result_chars": project_tool.max_result_chars,
                },
            )
        )
    return toolset


def build_scoped_toolset(catalog: ToolCatalog) -> FilteredToolset[AgentDeps]:
    """Hide tools that are absent from the injected catalog or denied per run."""
    toolset = build_project_function_toolset(catalog)

    def is_visible(ctx: RunContext[AgentDeps], tool_definition: Any) -> bool:
        project_tool = _find_tool(
            ctx.deps.services.tool_catalog, tool_definition.name
        )
        return (
            project_tool is not None
            and ctx.deps.permissions.allows(project_tool)
        )

    return toolset.filtered(is_visible)


def build_domain_toolset(
    catalog: ToolCatalog, scope: str
) -> AbstractToolset[AgentDeps]:
    """Build a statically narrowed company, market, or supply-chain toolset."""
    return build_scoped_toolset(catalog.for_scope(scope))


__all__ = [
    "ToolResultEnvelope",
    "build_domain_toolset",
    "build_project_function_toolset",
    "build_scoped_toolset",
]
