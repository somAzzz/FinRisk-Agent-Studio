"""Workflow API endpoints for the FinRisk Agent Studio.

Exposes three routes:
- ``POST /workflows/finrisk/run`` to start a run.
- ``GET /workflows/{run_id}`` for status + timeline data.
- ``GET /workflows/{run_id}/report`` for the final report markdown.

Background execution uses ``asyncio.create_task`` so the request
returns immediately. Exceptions are caught inside the task and
recorded on the workflow state.

Tests can opt out of background execution by setting the
``FINRISK_SKIP_BACKGROUND`` environment variable. When set, the
endpoint still creates the run and returns ``run_id``, but the caller
is responsible for driving the workflow.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _background_enabled() -> bool:
    return os.environ.get("FINRISK_SKIP_BACKGROUND") != "1"

from src.api.run_store import InMemoryRunStore
from src.workflows.finrisk_workflow import DEFAULT_FIXTURE_DIR, run_finrisk_workflow
from src.workflows.state import (
    FinRiskRequest,
    WorkflowEvaluation,
    WorkflowTraceEvent,
    utcnow,
)
from src.workflows.v16_runner import run_finrisk_workflow_v16

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows")

# A single in-memory store instance is shared across all requests.
_run_store = InMemoryRunStore()

# Keep the fixture path configurable; tests can swap it via set_fixture_path.
_fixture_path: Path = DEFAULT_FIXTURE_DIR / "aapl_demo_workflow.json"


def get_run_store() -> InMemoryRunStore:
    """Return the singleton store (exposed for tests)."""
    return _run_store


def set_fixture_path(path: Path) -> None:
    """Override the demo fixture path (used by tests)."""
    global _fixture_path
    _fixture_path = path


def get_fixture_path() -> Path:
    return _fixture_path


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------


class WorkflowRunSummary(BaseModel):
    """Lightweight summary returned by ``POST /workflows/finrisk/run``."""

    run_id: str
    status: str
    current_step: str | None = None
    started_at: str
    completed_at: str | None = None
    report_url: str | None = None


class WorkflowStatusResponse(BaseModel):
    """Returned by ``GET /workflows/{run_id}``."""

    run_id: str
    status: str
    current_step: str | None = None
    trace: list[WorkflowTraceEvent]
    company: Any | None = None
    risk_count: int
    evidence_count: int
    evaluation: WorkflowEvaluation | None = None
    completed_at: str | None = None


class WorkflowReportResponse(BaseModel):
    """Returned by ``GET /workflows/{run_id}/report``."""

    run_id: str
    status: str
    report: Any | None = None
    markdown: str | None = None
    evaluation: WorkflowEvaluation | None = None


# ---------------------------------------------------------------------------
# Background execution
# ---------------------------------------------------------------------------


async def _run_and_store(state) -> None:
    """Run the workflow and persist final state.

    The task catches every exception so the API never crashes the
    server loop. Failures are recorded on the state so callers can
    inspect them via ``GET /workflows/{run_id}``.
    """
    try:
        # Skip if a test or other caller already drove the workflow
        # synchronously. The store is shared, so the synchronous update
        # wins and we must not overwrite the completed state.
        existing = await _run_store.get(state.run_id)
        if existing is not None and existing.status == "completed":
            return
        state.status = "running"
        await _run_store.update(state)
        # v16: the v16 runner composes the v15 orchestrator with the
        # quality-layer engine and the graph-reasoning subsystem, so
        # all the v16 fields on the state are populated by the time
        # the request returns.
        finished = await run_finrisk_workflow_v16(
            state.request,
            fixture_path=get_fixture_path(),
            initial_state=state,
        )
        await _run_store.update(finished)
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow %s failed", state.run_id)
        state.status = "failed"
        state.trace.append(
            WorkflowTraceEvent(
                step_name="orchestrator",
                status="failed",
                started_at=utcnow(),
                completed_at=utcnow(),
                error=f"{type(exc).__name__}: {exc}",
            )
        )
        await _run_store.update(state)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/finrisk/run",
    response_model=WorkflowRunSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_workflow(request: FinRiskRequest) -> WorkflowRunSummary:
    """Start a new FinRisk workflow run."""
    state = await _run_store.create(request)
    if _background_enabled():
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(_run_and_store(state))
        else:
            asyncio.create_task(_run_and_store(state))
    return WorkflowRunSummary(
        run_id=state.run_id,
        status="queued",
        current_step=None,
        started_at=utcnow().isoformat(),
        completed_at=None,
        report_url=f"/workflows/{state.run_id}/report",
    )


@router.get("/health", response_model=dict)
async def health() -> dict:
    return {"status": "ok", "runs": await _run_store.size()}


@router.get("/{run_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(run_id: str) -> WorkflowStatusResponse:
    state = await _run_store.get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown run"
        )
    current_step = _current_step(state)
    return WorkflowStatusResponse(
        run_id=state.run_id,
        status=state.status,
        current_step=current_step,
        trace=state.trace,
        company=state.company.model_dump() if state.company else None,
        risk_count=len(state.filing_risks),
        evidence_count=len(state.normalized_evidence),
        evaluation=state.evaluation,
        completed_at=(
            state.trace[-1].completed_at.isoformat()
            if state.trace and state.trace[-1].completed_at
            else None
        ),
    )


@router.get("/{run_id}/report", response_model=WorkflowReportResponse)
async def get_workflow_report(run_id: str) -> WorkflowReportResponse:
    state = await _run_store.get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown run"
        )
    if state.report is None:
        # Run still in progress; return current status without a report.
        return WorkflowReportResponse(
            run_id=state.run_id,
            status=state.status,
            report=None,
            markdown=None,
            evaluation=state.evaluation,
        )
    return WorkflowReportResponse(
        run_id=state.run_id,
        status=state.status,
        report=state.report.model_dump(),
        markdown=state.report.markdown,
        evaluation=state.evaluation,
    )


def _current_step(state) -> str | None:
    """Return the most recent in-flight step name from the trace."""
    for event in reversed(state.trace):
        if event.status == "running":
            return event.step_name
    if state.status == "completed":
        return None
    completed = [e for e in state.trace if e.status == "completed"]
    return completed[-1].step_name if completed else None


# ---------------------------------------------------------------------------
# v16 routes
# ---------------------------------------------------------------------------


@router.get("/{run_id}/trace", response_model=dict)
async def get_workflow_trace(run_id: str) -> dict:
    """Return the v15 trace plus v16 fallback events."""
    state = await _run_store.get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown run"
        )
    return {
        "run_id": state.run_id,
        "trace": [e.model_dump(mode="json") for e in state.trace],
        "fallback_events": [
            (e.model_dump(mode="json") if hasattr(e, "model_dump") else e)
            for e in state.fallback_events
        ],
    }


@router.get("/{run_id}/graph", response_model=dict)
async def get_workflow_graph(run_id: str) -> dict:
    """Return the v16 evidence-graph payload."""
    state = await _run_store.get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown run"
        )
    return {
        "nodes": _as_list(state.graph_paths, "nodes"),
        "edges": _as_list(state.graph_paths, "edges"),
        "paths": list(state.graph_paths or []),
        "insights": [i.model_dump(mode="json") for i in state.graph_insights],
        "guardrail_findings": [
            f.model_dump(mode="json") for f in state.guardrail_findings
        ],
    }


@router.get("/{run_id}/evaluation", response_model=dict)
async def get_workflow_evaluation(run_id: str) -> dict:
    """Return the v16 workflow-level evaluation."""
    state = await _run_store.get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown run"
        )
    if state.workflow_evaluation is None:
        return {
            "run_id": state.run_id,
            "final_status": "pass",
            "overall_metrics": {},
            "blocker_count": 0,
            "warning_count": 0,
            "unsupported_claims": [],
            "human_review_required": False,
            "step_evaluations": [],
        }
    we = state.workflow_evaluation
    # v16 stores the Pydantic model on the state; convert to dict
    # for the API response. The model_validate / model_dump round
    # trip is intentional to keep the wire format stable.
    payload = we.model_dump(mode="json") if hasattr(we, "model_dump") else we
    return payload


@router.get("/{run_id}/artifacts", response_model=dict)
async def get_workflow_artifacts(run_id: str) -> dict:
    """Return the v16 artifacts dict (paths to generated files)."""
    state = await _run_store.get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown run"
        )
    return {
        "run_id": state.run_id,
        "artifacts": dict(state.artifacts or {}),
    }


def _as_list(graph_paths: Any, key: str) -> list:
    """Flatten a list of path dicts into a single list of nodes/edges."""
    if not graph_paths:
        return []
    out: list = []
    for path in graph_paths:
        if isinstance(path, dict):
            out.extend(path.get(key, []))
        else:
            out.extend(getattr(path, key, []))
    return out


__all__ = [
    "router",
    "WorkflowRunSummary",
    "WorkflowStatusResponse",
    "WorkflowReportResponse",
    "get_run_store",
    "set_fixture_path",
    "get_fixture_path",
]