"""API tests for the FinRisk Agent Studio workflow endpoints.

Tests bypass ``TestClient`` and call the route handlers directly so
pytest-asyncio's event loop drives both the workflow and the API in
the same loop. This avoids the well-known ``asyncio.create_task`` race
between TestClient and the test coroutine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api.workflows import (
    get_run_store,
    get_workflow_report,
    get_workflow_status,
    set_fixture_path,
    start_workflow,
)
from src.schemas.finrisk import FinRiskRequest
from src.workflows.finrisk_workflow import run_finrisk_workflow

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "finrisk"
    / "aapl_demo_workflow.json"
)


@pytest.fixture(autouse=True)
def _reset_store_and_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the in-memory store between tests and disable background."""
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    store = get_run_store()
    store._states.clear()  # type: ignore[attr-defined]
    set_fixture_path(FIXTURE_PATH)
    yield


async def _drive_workflow_inline(run_id: str) -> None:
    """Run the workflow inline on the current event loop."""
    store = get_run_store()
    state = await store.get(run_id)
    if state is None or state.status == "completed":
        return
    finished = await run_finrisk_workflow(
        state.request,
        fixture_path=FIXTURE_PATH,
        initial_state=state,
    )
    await store.update(finished)


async def _start_and_drive(payload: dict) -> str:
    """Start a workflow and drive it to completion inline."""
    summary = await start_workflow(FinRiskRequest.model_validate(payload))
    await _drive_workflow_inline(summary.run_id)
    return summary.run_id


async def test_start_workflow_returns_run_id() -> None:
    payload = {
        "ticker": "AAPL",
        "analysis_goal": "Identify macro, policy and supply-chain risks.",
        "demo_mode": True,
    }
    summary = await start_workflow(FinRiskRequest.model_validate(payload))
    assert summary.run_id.startswith("run-")
    assert summary.status == "queued"
    assert summary.report_url.endswith("/report")


async def test_workflow_completes_when_drove_inline() -> None:
    run_id = await _start_and_drive(
        {
            "ticker": "AAPL",
            "analysis_goal": "Identify risks.",
            "demo_mode": True,
        }
    )
    response = await get_workflow_status(run_id)
    assert response.status == "completed"


async def test_status_endpoint_returns_full_trace() -> None:
    run_id = await _start_and_drive(
        {
            "ticker": "AAPL",
            "analysis_goal": "Identify risks.",
            "demo_mode": True,
        }
    )
    response = await get_workflow_status(run_id)
    assert len(response.trace) == 9
    assert response.risk_count >= 3
    assert response.evidence_count >= 3
    assert response.company is not None
    assert response.company["ticker"] == "AAPL"
    assert response.evaluation is not None


async def test_report_endpoint_returns_markdown() -> None:
    run_id = await _start_and_drive(
        {
            "ticker": "AAPL",
            "analysis_goal": "Identify risks.",
            "demo_mode": True,
        }
    )
    response = await get_workflow_report(run_id)
    assert response.status == "completed"
    assert response.markdown is not None
    assert "## Executive Summary" in response.markdown
    assert response.evaluation is not None
    assert response.evaluation.final_status in {"pass", "needs_review", "fail"}


async def test_unknown_run_returns_404_on_status() -> None:
    with pytest.raises(Exception) as exc_info:
        await get_workflow_status("run-does-not-exist")
    assert exc_info.value.status_code == 404


async def test_unknown_run_returns_404_on_report() -> None:
    with pytest.raises(Exception) as exc_info:
        await get_workflow_report("run-does-not-exist")
    assert exc_info.value.status_code == 404


def test_invalid_request_validation_rejects_empty_goal() -> None:
    """Empty goal is caught by the Pydantic model itself, not the route."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FinRiskRequest.model_validate(
            {"ticker": "AAPL", "analysis_goal": "   "}
        )


def test_invalid_request_validation_rejects_missing_ticker() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FinRiskRequest.model_validate({"analysis_goal": "x"})


async def test_run_count_increments_after_run() -> None:
    store = get_run_store()
    before = await store.size()
    await _start_and_drive(
        {
            "ticker": "AAPL",
            "analysis_goal": "Identify risks.",
            "demo_mode": True,
        }
    )
    after = await store.size()
    assert after == before + 1


async def test_in_flight_state_status_is_not_yet_completed() -> None:
    """Without driving the workflow, status remains queued/created."""
    summary = await start_workflow(
        FinRiskRequest.model_validate(
            {
                "ticker": "AAPL",
                "analysis_goal": "Identify risks.",
                "demo_mode": True,
            }
        )
    )
    response = await get_workflow_status(summary.run_id)
    assert response.status in {"created", "running"}


async def test_health_endpoint_reports_run_count() -> None:
    from src.api.workflows import health

    response = await health()
    assert response["status"] == "ok"
    assert response["runs"] >= 0
