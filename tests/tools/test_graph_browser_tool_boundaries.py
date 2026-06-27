"""Boundaries for LLM-visible graph and browser tools."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from src.tools.catalog import build_project_tool_catalog


def _schema_for(catalog, name: str) -> dict[str, Any]:
    return next(
        tool["function"]["parameters"]
        for tool in catalog.tools
        if tool["function"]["name"] == name
    )


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def test_graph_tools_are_structured_read_only_tools() -> None:
    catalog = build_project_tool_catalog(scope="supply_chain")

    assert "graph_query" in catalog.names
    assert "graph_path_search" in catalog.names
    assert all(tool.risk_level != "write_gated" for tool in catalog.project_tools)
    assert not _contains_key(_schema_for(catalog, "graph_query"), "cypher")
    assert not _contains_key(_schema_for(catalog, "graph_path_search"), "cypher")

    result = catalog.tool_map["graph_query"](entity="AAPL", max_hops=2)

    assert result["status"] == "success"
    assert result["data"]["paths"]
    assert result["evidence_kind"] == "graph_path"


def test_graph_path_search_filters_fixture_paths() -> None:
    catalog = build_project_tool_catalog(scope="finrisk_market")

    result = catalog.tool_map["graph_path_search"](
        source_entity="AAPL",
        target_entity="TSMC",
        max_hops=3,
    )

    paths = result["data"]["paths"]
    assert paths
    assert all("TSMC" in path["path_text"] for path in paths)


def test_browser_explore_exposes_only_bounded_explorer() -> None:
    class FakeExplorer:
        def explore(self, goal: str, initial_urls=None):
            return SimpleNamespace(
                goal=goal,
                current_step=1,
                findings=[
                    {
                        "url": "https://example.com",
                        "summary": "example finding",
                    }
                ],
                visited_urls=initial_urls or [],
            )

    catalog = build_project_tool_catalog(
        browser_explorer=FakeExplorer(),
        scope="finrisk_market",
    )
    schema = _schema_for(catalog, "browser_explore")

    assert "browser_explore" in catalog.names
    assert not _contains_key(schema, "click")
    assert not _contains_key(schema, "scroll")
    assert not _contains_key(schema, "selector")

    result = catalog.tool_map["browser_explore"](
        goal="inspect source",
        initial_urls=["https://example.com"],
        max_steps=2,
    )

    assert result["status"] == "success"
    assert result["data"]["current_step"] == 1
    assert result["data"]["findings"][0]["summary"] == "example finding"
    assert result["evidence_kind"] == "browser"
