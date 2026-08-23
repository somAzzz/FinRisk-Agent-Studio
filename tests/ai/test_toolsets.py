"""Contract and permission tests for typed Pydantic AI toolsets."""

from __future__ import annotations

from pydantic_ai import RunContext, RunUsage
from pydantic_ai.models.test import TestModel

from src.ai.deps import AgentDeps, AgentPermissions, AgentServices
from src.ai.toolsets import (
    ToolResultEnvelope,
    build_project_function_toolset,
    build_scoped_toolset,
)
from src.config import Settings
from src.tools.catalog import build_project_tool_catalog
from src.tools.contracts import ProjectTool, ToolCatalog


def _context(deps: AgentDeps) -> RunContext[AgentDeps]:
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage())


def test_all_legacy_tools_have_typed_schema_and_metadata_parity() -> None:
    catalog = build_project_tool_catalog(scope=None)
    toolset = build_project_function_toolset(catalog)

    assert list(toolset.tools) == catalog.names
    for project_tool in catalog.project_tools:
        typed_tool = toolset.tools[project_tool.name]
        typed_schema = typed_tool.tool_def.parameters_json_schema
        assert set(typed_schema["properties"]) == set(
            project_tool.parameters["properties"]
        )
        assert set(typed_schema.get("required", [])) == set(
            project_tool.parameters.get("required", [])
        )
        assert typed_schema["additionalProperties"] is False
        assert typed_tool.metadata == {
            "scopes": sorted(project_tool.scopes),
            "risk_level": project_tool.risk_level,
            "evidence_kind": project_tool.evidence_kind,
            "max_result_chars": project_tool.max_result_chars,
        }


async def test_scoped_toolset_hides_interactive_and_wrong_scope_tools() -> None:
    catalog = build_project_tool_catalog(scope=None)
    deps = AgentDeps(
        run_id="scope-1",
        settings=Settings(),
        permissions=AgentPermissions(
            tool_scopes=frozenset({"finrisk_market"}),
            allow_interactive=False,
        ),
        services=AgentServices(tool_catalog=catalog),
    )

    visible = await build_scoped_toolset(catalog).get_tools(_context(deps))

    assert "web_search" in visible
    assert "browser_explore" not in visible
    assert "sec_list_filings" not in visible


async def test_typed_wrapper_preserves_envelope_and_records_event() -> None:
    project_tool = ProjectTool(
        name="web_search",
        description="Search.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        callable=lambda query, **_: {"query": query},
        scopes=frozenset({"company_research"}),
        evidence_kind="web",
    )
    catalog = ToolCatalog(project_tools=(project_tool,))
    deps = AgentDeps(
        run_id="tool-1",
        settings=Settings(),
        services=AgentServices(tool_catalog=catalog),
    )
    toolset = build_scoped_toolset(catalog)
    ctx = _context(deps)
    tools = await toolset.get_tools(ctx)

    result = await toolset.call_tool(
        "web_search", {"query": "AAPL"}, ctx, tools["web_search"]
    )

    assert isinstance(result, ToolResultEnvelope)
    assert result.status == "success"
    assert result.data == {"query": "AAPL"}
    assert deps.services.tool_events[0].tool_name == "web_search"
    assert deps.services.tool_events[0].status == "success"


async def test_direct_tool_call_is_denied_even_if_visibility_is_bypassed() -> None:
    project_tool = ProjectTool(
        name="browser_explore",
        description="Browse.",
        parameters={
            "type": "object",
            "properties": {"goal": {"type": "string"}},
            "required": ["goal"],
        },
        callable=lambda goal, **_: {"goal": goal},
        risk_level="interactive",
        scopes=frozenset({"company_research"}),
    )
    catalog = ToolCatalog(project_tools=(project_tool,))
    deps = AgentDeps(
        run_id="tool-denied",
        settings=Settings(),
        services=AgentServices(tool_catalog=catalog),
    )
    unfiltered = build_project_function_toolset(catalog)
    ctx = _context(deps)
    tools = await unfiltered.get_tools(ctx)

    result = await unfiltered.call_tool(
        "browser_explore",
        {"goal": "open page"},
        ctx,
        tools["browser_explore"],
    )

    assert result.status == "failed"
    assert "PermissionError" in (result.error or "")
    assert deps.services.tool_events[0].status == "failed"
