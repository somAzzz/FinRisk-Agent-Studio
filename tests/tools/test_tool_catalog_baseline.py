"""Regression gate for the pre-Pydantic-AI tool catalog contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.tools.catalog import build_project_tool_catalog
from src.tools.contracts import ProjectTool

BASELINE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "pydantic_ai_migration"
    / "tool_catalog_baseline.json"
)


def _tool_snapshot(tool: ProjectTool) -> dict[str, Any]:
    parameters = tool.parameters
    canonical_schema = json.dumps(
        tool.openai_schema,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return {
        "name": tool.name,
        "scopes": sorted(tool.scopes),
        "risk_level": tool.risk_level,
        "evidence_kind": tool.evidence_kind,
        "max_result_chars": tool.max_result_chars,
        "required": sorted(parameters.get("required", [])),
        "properties": sorted(parameters.get("properties", {})),
        "schema_sha256": hashlib.sha256(canonical_schema).hexdigest(),
    }


def test_tool_catalog_matches_pai_0_baseline() -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    catalog = build_project_tool_catalog(scope=None)
    actual = [_tool_snapshot(tool) for tool in catalog.project_tools]

    assert baseline["schema_version"] == 1
    assert baseline["tool_count"] == len(actual) == 13
    assert baseline["tools"] == actual
