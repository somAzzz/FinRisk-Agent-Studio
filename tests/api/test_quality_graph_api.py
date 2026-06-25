"""Tests for the v16 quality / graph API endpoints."""

from __future__ import annotations

import pytest

from src.api.workflows import (
    get_run_store,
    get_workflow_artifacts,
    get_workflow_evaluation,
    get_workflow_graph,
    get_workflow_report,
    get_workflow_status,
    get_workflow_trace,
    set_fixture_path,
    start_workflow,
)
from src.schemas.finrisk import FinRiskRequest
from src.workflows.finrisk_workflow import run_finrisk_workflow
from src.workflows.v16_runner import run_finrisk_workflow_v16
from pathlib import Path
import os


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


async def _start_and_drive_v16(payload: dict) -> str:
    summary = await start_workflow(FinRiskRequest.model_validate(payload))
    store = get_run_store()
    state = await store.get(summary.run_id)
    finished = await run_finrisk_workflow_v16(
        state.request,
        fixture_path=FIXTURE_PATH,
        initial_state=state,
    )
    await store.update(finished)
    return summary.run_id


async def test_trace_endpoint_returns_trace_and_fallback_events() -> None:
    run_id = await _start_and_drive_v16(
        {"ticker": "AAPL", "analysis_goal": "test", "demo_mode": True}
    )
    payload = await get_workflow_trace(run_id)
    assert payload["run_id"] == run_id
    assert isinstance(payload["trace"], list) and payload["trace"]
    assert "fallback_events" in payload


async def test_graph_endpoint_returns_v16_payload() -> None:
    run_id = await _start_and_drive_v16(
        {"ticker": "AAPL", "analysis_goal": "test", "demo_mode": True}
    )
    payload = await get_workflow_graph(run_id)
    assert "nodes" in payload and "edges" in payload
    assert "paths" in payload and "insights" in payload
    assert "guardrail_findings" in payload


async def test_evaluation_endpoint_returns_v16_summary() -> None:
    run_id = await _start_and_drive_v16(
        {"ticker": "AAPL", "analysis_goal": "test", "demo_mode": True}
    )
    payload = await get_workflow_evaluation(run_id)
    assert payload["run_id"] == run_id
    assert "final_status" in payload
    assert "step_evaluations" in payload
    assert "overall_metrics" in payload
    assert "blocker_count" in payload
    assert "warning_count" in payload


async def test_artifacts_endpoint_returns_dict() -> None:
    run_id = await _start_and_drive_v16(
        {"ticker": "AAPL", "analysis_goal": "test", "demo_mode": True}
    )
    payload = await get_workflow_artifacts(run_id)
    assert payload["run_id"] == run_id
    assert "artifacts" in payload


async def test_v16_endpoints_404_for_unknown_run() -> None:
    for fn in (
        get_workflow_trace,
        get_workflow_graph,
        get_workflow_evaluation,
        get_workflow_artifacts,
    ):
        with pytest.raises(Exception) as exc:
            await fn("run-does-not-exist")
        assert exc.value.status_code == 404


async def test_v16_runner_persists_workflow_evaluation() -> None:
    run_id = await _start_and_drive_v16(
        {"ticker": "AAPL", "analysis_goal": "test", "demo_mode": True}
    )
    store = get_run_store()
    state = await store.get(run_id)
    assert state.workflow_evaluation is not None
    # Evaluations are recorded for every step.
    assert len(state.evaluations) >= 1
