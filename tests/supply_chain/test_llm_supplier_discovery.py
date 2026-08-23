"""LLM-driven supplier discovery migration tests."""

from __future__ import annotations

from src.tools.catalog import build_project_tool_catalog


def test_supply_chain_llm_catalog_excludes_write_tools() -> None:
    catalog = build_project_tool_catalog(scope="supply_chain")
    assert "web_search" in catalog.names
    assert "sec_fetch_filing" in catalog.names
    assert "graph_write" not in catalog.names
    assert all(tool.risk_level != "write_gated" for tool in catalog.project_tools)
