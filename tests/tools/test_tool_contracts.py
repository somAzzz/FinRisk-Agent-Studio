import json

import pytest

from src.tools.catalog import build_project_tool_catalog
from src.tools.contracts import ProjectTool, ToolCatalog, jsonable, truncate_jsonable


def test_project_tool_openai_schema_shape() -> None:
    tool = ProjectTool(
        name="example_lookup",
        description="Lookup example data.",
        parameters={
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
        callable=lambda ticker: {"ticker": ticker},
        evidence_kind="financial_metric",
    )

    assert tool.openai_schema == {
        "type": "function",
        "function": {
            "name": "example_lookup",
            "description": "Lookup example data.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
        },
    }


def test_project_tool_executable_returns_json_envelope() -> None:
    tool = ProjectTool(
        name="example_lookup",
        description="Lookup example data.",
        parameters={"type": "object", "properties": {}},
        callable=lambda: {"value": 42},
        evidence_kind="financial_metric",
    )

    result = tool.executable()()

    assert result == {
        "tool": "example_lookup",
        "status": "success",
        "data": {"value": 42},
        "evidence_kind": "financial_metric",
        "warnings": [],
        "truncated": False,
    }
    json.dumps(result)


def test_project_tool_rejects_write_gated_default_scope() -> None:
    with pytest.raises(ValueError, match="write_gated"):
        ProjectTool(
            name="graph_write",
            description="Write graph.",
            parameters={"type": "object", "properties": {}},
            callable=lambda: "ok",
            risk_level="write_gated",
        )


def test_tool_catalog_schema_names_match_tool_map() -> None:
    catalog = build_project_tool_catalog()

    schema_names = [tool["function"]["name"] for tool in catalog.tools]

    assert schema_names == catalog.names
    assert set(catalog.tool_map) == set(catalog.names)
    assert all(tool["type"] == "function" for tool in catalog.tools)
    assert all("input_schema" not in tool for tool in catalog.tools)


def test_default_catalog_excludes_write_gated_tools() -> None:
    catalog = build_project_tool_catalog()

    assert all(tool.risk_level != "write_gated" for tool in catalog.project_tools)


def test_catalog_select_and_scope_preserve_project_tool_metadata() -> None:
    alpha = ProjectTool(
        name="alpha",
        description="Alpha",
        parameters={"type": "object", "properties": {}},
        callable=lambda: "alpha",
        scopes=frozenset({"default", "finrisk"}),
    )
    beta = ProjectTool(
        name="beta",
        description="Beta",
        parameters={"type": "object", "properties": {}},
        callable=lambda: "beta",
        scopes=frozenset({"supply_chain"}),
    )
    catalog = ToolCatalog(project_tools=(alpha, beta))

    assert catalog.select(["beta"]).names == ["beta"]
    assert catalog.for_scope("finrisk").names == ["alpha"]
    assert catalog.for_scope("supply_chain").names == ["beta"]


def test_jsonable_and_truncation_helpers() -> None:
    value = jsonable({"items": [object()]})
    truncated, did_truncate = truncate_jsonable(value, max_chars=10)

    assert did_truncate is True
    assert truncated["original_chars"] > 10
    assert "truncated_text" in truncated
