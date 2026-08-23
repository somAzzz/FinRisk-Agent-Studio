"""Tests for typed Pydantic AI dependencies and permission filtering."""

from src.ai.deps import AgentDeps, AgentPermissions, AgentServices
from src.config import Settings
from src.tools.contracts import ProjectTool, ToolCatalog


def _tool(name: str, *, scope: str, risk_level: str = "read_only") -> ProjectTool:
    return ProjectTool(
        name=name,
        description=name,
        parameters={"type": "object", "properties": {}},
        callable=lambda: name,
        scopes=frozenset({scope}),
        risk_level=risk_level,  # type: ignore[arg-type]
    )


def test_visible_catalog_filters_scope_and_risk() -> None:
    catalog = ToolCatalog(
        project_tools=(
            _tool("read", scope="company_research"),
            _tool("browser", scope="company_research", risk_level="interactive"),
            _tool("other", scope="supply_chain"),
        )
    )
    deps = AgentDeps(
        run_id="run-1",
        settings=Settings(),
        permissions=AgentPermissions(tool_scopes=frozenset({"company_research"})),
        services=AgentServices(tool_catalog=catalog),
    )

    assert deps.visible_tool_catalog().names == ["read"]


def test_interactive_tool_requires_explicit_permission() -> None:
    tool = _tool("browser", scope="company_research", risk_level="interactive")
    permissions = AgentPermissions(
        tool_scopes=frozenset({"company_research"}),
        allow_interactive=True,
    )

    assert permissions.allows(tool) is True
