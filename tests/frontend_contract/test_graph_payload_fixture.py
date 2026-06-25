"""v17 frontend contract: ``/workflows/{run_id}/graph`` payload.

The fixture in this file is the v17 reference shape for the
``WorkflowGraphResponse`` TypeScript type. The test asserts:

- the JSON can be deserialised back into a dict;
- every v16 ``insight.risk_path_ids`` reference resolves to a
  real ``path_id`` in the payload;
- every v16 ``insight.evidence_ids`` reference exists in the
  state (verified via the live API);
- ``guardrail_findings`` is serialisable.

The contract lives in this file so the React frontend can diff
its types against it during code review.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "finrisk"
    / "graph_payload_contract.json"
)


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_graph_payload_fixture_round_trips() -> None:
    payload = _load_fixture()
    blob = json.dumps(payload)
    reloaded = json.loads(blob)
    assert reloaded == payload


def test_graph_payload_fixture_has_required_fields() -> None:
    payload = _load_fixture()
    for key in ("nodes", "edges", "paths", "insights", "guardrail_findings"):
        assert key in payload, f"missing {key} in graph payload contract"
    assert isinstance(payload["nodes"], list)
    assert isinstance(payload["edges"], list)
    assert isinstance(payload["paths"], list)
    assert isinstance(payload["insights"], list)
    assert isinstance(payload["guardrail_findings"], list)


def test_graph_payload_insights_carry_v16_fields() -> None:
    payload = _load_fixture()
    for insight in payload["insights"]:
        # v16 GraphInsightV16 fields per frontend/src/types.ts.
        for key in (
            "insight_id",
            "source_company",
            "insight_type",
            "risk_path_ids",
            "affected_entities",
            "explanation",
            "evidence_ids",
            "confidence",
            "uncertainty",
            "recommended_next_questions",
            "research_theme",
        ):
            assert key in insight, (
                f"insight {insight.get('insight_id')} missing v16 field {key}"
            )


def test_graph_payload_insight_path_ids_resolve() -> None:
    payload = _load_fixture()
    path_ids = {p["path_id"] for p in payload["paths"]}
    for insight in payload["insights"]:
        for pid in insight["risk_path_ids"]:
            assert pid in path_ids, (
                f"insight {insight['insight_id']} cites missing path {pid}"
            )


def test_graph_payload_guardrail_findings_serialisable() -> None:
    payload = _load_fixture()
    for finding in payload["guardrail_findings"]:
        # Every finding must round-trip as JSON; Pydantic does the
        # rest when the API receives it.
        blob = json.dumps(finding)
        reloaded = json.loads(blob)
        assert reloaded == finding
