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

from src.api.store_factory import get_run_store as _factory_get_run_store
from src.workflows.finrisk_workflow import DEFAULT_FIXTURE_DIR
from src.workflows.state import (
    FinRiskRequest,
    WorkflowEvaluation,
    WorkflowTraceEvent,
    utcnow,
)
from src.workflows.v16_runner import run_finrisk_workflow_v16

logger = logging.getLogger(__name__)


def _background_enabled() -> bool:
    return os.environ.get("FINRISK_SKIP_BACKGROUND") != "1"


router = APIRouter(prefix="/workflows")

# The run-store backend is selected by ``RUN_STORE_BACKEND`` env var
# (see :mod:`src.api.store_factory`). The factory caches the backend
# per process; tests that need a fresh in-memory store can call
# :func:`reset_run_store_for_tests` (re-exported below for backwards
# compat) or monkeypatch the env before the first access.
_run_store = _factory_get_run_store()

# Retain strong references to background tasks so the event loop
# doesn't garbage-collect them mid-flight. Mirrors the pattern in
# ``src.api.supply_chain._background_tasks``.
_background_tasks: set[asyncio.Task] = set()

# Keep the fixture path configurable; tests can swap it via set_fixture_path.
_fixture_path: Path = DEFAULT_FIXTURE_DIR / "aapl_demo_workflow.json"


def get_run_store():
    """Return the singleton store (exposed for tests)."""
    return _run_store


def reset_run_store_for_tests() -> None:
    """Drop the cached backend. Test-only helper.

    Re-exported from :mod:`src.api.store_factory` so existing test
    imports (``from src.api.workflows import reset_run_store_for_tests``)
    keep working.
    """
    from src.api.store_factory import reset_run_store_for_tests as _reset

    _reset()


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
    report_v16: Any | None = None
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
        finished = await asyncio.to_thread(
            _run_workflow_sync,
            state,
            get_fixture_path(),
        )
        await _run_store.update(finished)
    except Exception as exc:
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


def _run_workflow_sync(state, fixture_path: Path):
    """Run the blocking workflow in a worker thread.

    The workflow is async at the orchestration boundary, but its live
    SEC and local-LLM clients perform synchronous I/O. Running it on the
    FastAPI event loop starves status polling during real-mode runs.
    """
    return asyncio.run(
        run_finrisk_workflow_v16(
            state.request,
            fixture_path=fixture_path,
            initial_state=state,
        )
    )


def _schedule_background(coro) -> None:
    """Schedule ``coro`` on the running loop and retain a strong
    reference so it isn't garbage-collected mid-flight.

    Mirrors :func:`src.api.supply_chain._schedule`.
    """
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


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
        _schedule_background(_run_and_store(state))
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
            report_v16=None,
            markdown=None,
            evaluation=state.evaluation,
        )
    return WorkflowReportResponse(
        run_id=state.run_id,
        status=state.status,
        report=state.report.model_dump(),
        report_v16=state.report_v16,
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
        # Per-step observability slices (added 2026-06-25). Each step's
        # contribution is rendered by the frontend ``StepOutputInspector``.
        "llm_log": [c.model_dump(mode="json") for c in state.llm_log],
        "chunk_validations": [
            c.model_dump(mode="json") for c in state.chunk_validations
        ],
        "section_locations": [
            s.model_dump(mode="json") for s in state.section_locations
        ],
        "risk_lifecycles": [
            a.model_dump(mode="json") for a in state.risk_lifecycles
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
        # P2.1: paths are now typed ``list[CandidateGraphPath]``;
        # serialise to JSON-friendly dicts so the existing client
        # contract (``p["path_id"]``) keeps working.
        "paths": [
            p.model_dump(mode="json") if hasattr(p, "model_dump") else p
            for p in (state.graph_paths or [])
        ],
        # v17 alignment: serve the v16 ``GraphInsightV16`` list when
        # present (each entry has ``risk_path_ids`` and
        # ``affected_entities``); fall back to the v15 ``GraphInsight``
        # dump for backward compatibility with existing clients.
        "insights": _v16_insights(state),
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


# ---------------------------------------------------------------------------
# Per-step observability routes (added 2026-06-25)
# ---------------------------------------------------------------------------


@router.get("/{run_id}/llm_log", response_model=dict)
async def get_workflow_llm_log(run_id: str) -> dict:
    """Return every :class:`LLMCall` row emitted by the workflow."""
    state = await _run_store.get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown run"
        )
    return {
        "run_id": state.run_id,
        "llm_log": [c.model_dump(mode="json") for c in state.llm_log],
    }


@router.get("/{run_id}/chunks", response_model=dict)
async def get_workflow_chunks(run_id: str) -> dict:
    """Return every :class:`ChunkValidation` row from the workflow."""
    state = await _run_store.get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown run"
        )
    return {
        "run_id": state.run_id,
        "chunk_validations": [
            c.model_dump(mode="json") for c in state.chunk_validations
        ],
    }


@router.get("/{run_id}/sections", response_model=dict)
async def get_workflow_sections(run_id: str) -> dict:
    """Return every :class:`SectionLocation` row from the workflow."""
    state = await _run_store.get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown run"
        )
    return {
        "run_id": state.run_id,
        "section_locations": [
            s.model_dump(mode="json") for s in state.section_locations
        ],
    }


@router.get("/{run_id}/lifecycles", response_model=dict)
async def get_workflow_lifecycles(run_id: str) -> dict:
    """Return every :class:`RiskLifecycleAnnotation` row from the workflow."""
    state = await _run_store.get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown run"
        )
    return {
        "run_id": state.run_id,
        "risk_lifecycles": [
            a.model_dump(mode="json") for a in state.risk_lifecycles
        ],
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


def _v16_insights(state) -> list[dict]:
    """Return the v16 ``GraphInsightV16`` list when present.

    Falls back to the v15 ``GraphInsight`` dump for backward
    compatibility with clients that pre-date v17. The fallback path
    adds an empty ``risk_path_ids`` list so the response shape is
    stable.
    """
    v16 = getattr(state, "graph_insights_v16", None) or []
    if v16:
        return [i if isinstance(i, dict) else i.model_dump(mode="json") for i in v16]
    out: list[dict] = []
    for ins in state.graph_insights:
        dumped = ins.model_dump(mode="json")
        dumped.setdefault("risk_path_ids", [])
        dumped.setdefault("affected_entities", [dumped.get("affected_entity", "")])
        dumped.setdefault("research_theme", dumped.get("investment_theme"))
        out.append(dumped)
    return out


__all__ = [
    "WorkflowReportResponse",
    "WorkflowRunSummary",
    "WorkflowStatusResponse",
    "get_fixture_path",
    "get_run_store",
    "reset_run_store_for_tests",
    "router",
    "set_fixture_path",
]
