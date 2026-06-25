"""End-to-end contract tests between the v16 graph/eval/report payload
and the frontend TypeScript types.

These tests are the v17 alignment gate: the API response shape must
match the ``WorkflowGraphResponse`` / ``WorkflowEvaluationResponse``
types declared in ``frontend/src/types.ts``. Every insight must
reference real ``path_id`` and ``evidence_id`` values, and the guardrail
findings must point at concrete affected objects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api.workflows import (
    get_run_store,
    set_fixture_path,
    start_workflow,
)
from src.schemas.finrisk import FinRiskRequest
from src.workflows.v16_runner import run_finrisk_workflow_v16


FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "finrisk"
    / "aapl_demo_workflow.json"
)


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    store = get_run_store()
    store._states.clear()  # type: ignore[attr-defined]
    set_fixture_path(FIXTURE_PATH)
    yield


async def _start_and_drive() -> str:
    summary = await start_workflow(
        FinRiskRequest.model_validate(
            {"ticker": "AAPL", "analysis_goal": "test", "demo_mode": True}
        )
    )
    store = get_run_store()
    state = await store.get(summary.run_id)
    finished = await run_finrisk_workflow_v16(
        state.request,
        fixture_path=FIXTURE_PATH,
        initial_state=state,
    )
    await store.update(finished)
    return summary.run_id


async def test_graph_insights_carry_v16_fields() -> None:
    from src.api.workflows import get_workflow_graph

    run_id = await _start_and_drive()
    payload = await get_workflow_graph(run_id)
    insights = payload["insights"]
    assert insights, "expected at least one v16 insight"
    sample = insights[0]
    # v16 contract: every insight must carry the v16-only fields.
    assert "risk_path_ids" in sample
    assert "affected_entities" in sample
    assert "research_theme" in sample or sample.get("research_theme") is None


async def test_insight_path_ids_exist_in_payload() -> None:
    from src.api.workflows import get_workflow_graph

    run_id = await _start_and_drive()
    payload = await get_workflow_graph(run_id)
    path_ids = {p["path_id"] for p in payload["paths"]}
    for insight in payload["insights"]:
        for pid in insight.get("risk_path_ids", []):
            assert pid in path_ids, (
                f"insight {insight.get('insight_id')} cites missing path {pid}"
            )


async def test_insight_evidence_ids_exist_in_state() -> None:
    from src.api.workflows import get_workflow_graph

    run_id = await _start_and_drive()
    payload = await get_workflow_graph(run_id)
    state = await get_run_store().get(run_id)
    valid = {ev.evidence_id for ev in state.normalized_evidence}
    for insight in payload["insights"]:
        for eid in insight.get("evidence_ids", []):
            assert eid in valid, (
                f"insight cites unknown evidence {eid}"
            )


async def test_evaluation_summary_has_step_evaluations() -> None:
    from src.api.workflows import get_workflow_evaluation

    run_id = await _start_and_drive()
    payload = await get_workflow_evaluation(run_id)
    assert payload["final_status"] in {"pass", "warning", "needs_review", "fail"}
    assert payload["step_evaluations"]
    step_names = {s["step_name"] for s in payload["step_evaluations"]}
    # The 8 default steps must each produce an evaluation.
    expected = {
        "company_resolver",
        "filing_risk_extractor",
        "market_explorer",
        "evidence_normalizer",
        "risk_scorer",
        "graph_reasoner",
        "report_generator",
        "evaluator",
    }
    assert expected.issubset(step_names)


async def test_evaluation_blocker_count_matches_findings() -> None:
    from src.api.workflows import get_workflow_evaluation

    run_id = await _start_and_drive()
    payload = await get_workflow_evaluation(run_id)
    expected = sum(
        1
        for s in payload["step_evaluations"]
        for f in s["findings"]
        if f["severity"] == "blocker"
    )
    assert payload["blocker_count"] == expected


async def test_report_endpoint_returns_v16_report() -> None:
    """The /report endpoint must surface the v16 structured report."""
    from src.api.workflows import get_workflow_report

    run_id = await _start_and_drive()
    payload = (await get_workflow_report(run_id)).model_dump()
    assert payload["report_v16"] is not None
    r16 = payload["report_v16"]
    # v16 contract: scores are 0-100, the report carries a
    # disclaimer, and every top risk has evidence ids.
    assert r16["disclaimer"].lower().startswith("disclaimer")
    assert r16["top_risks"]
    for item in r16["top_risks"]:
        assert 0.0 <= item["final_score"] <= 100.0
        assert item["supporting_evidence_ids"]


async def test_score_breakdown_uses_v16_zero_to_hundred() -> None:
    """The v16 risk score on the state must use 0-100 scale."""
    run_id = await _start_and_drive()
    state = await get_run_store().get(run_id)
    assert state is not None
    for score in state.risk_scores_v16:
        # v17: scores are Pydantic models, not dicts.
        assert 0.0 <= score.final_score <= 100.0
        # Per spec the breakdown must include every component.
        for key in (
            "base_severity",
            "recent_signal_strength",
            "evidence_quality",
            "source_diversity",
            "novelty_score",
            "graph_centrality",
        ):
            assert key in score.score_breakdown


async def test_graph_findings_can_be_located() -> None:
    """Every graph_path finding should reference a real path id."""
    from src.api.workflows import get_workflow_graph

    run_id = await _start_and_drive()
    payload = await get_workflow_graph(run_id)
    path_ids = {p["path_id"] for p in payload["paths"]}
    for f in payload["guardrail_findings"]:
        if f["affected_object_type"] == "graph_path":
            assert f["affected_object_id"] in path_ids, (
                f"finding {f['finding_id']} references unknown path "
                f"{f['affected_object_id']}"
            )
