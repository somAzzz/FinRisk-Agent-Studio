"""V21 local agent-run API routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.planner import AgentPlanner
from src.agents.state import AgentRunState, AgentWorkflowKind, HumanReviewItem, _now
from src.security.redaction import redact_obj

router = APIRouter(prefix="/agent-runs")

ReviewAction = Literal["approve", "reject", "comment"]

_agent_runs: dict[str, AgentRunState] = {}
_agent_runtime: GlobalAgentRuntime | None = None


class AgentRunRequest(BaseModel):
    """Request body for starting a V21 agent run."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)
    workflow_kind: AgentWorkflowKind = "generic_research"
    provider: str | None = None
    tool_loop_mode: str | None = None
    tool_scope: str | None = None
    demo_mode: bool = False
    cached_mode: bool = False
    subject: dict[str, Any] = Field(default_factory=dict)


class AgentRunSummary(BaseModel):
    """Lightweight response for a newly started agent run."""

    run_id: str
    status: str
    timeline_url: str
    trace_url: str


class AgentRunTimeline(BaseModel):
    """UI-friendly timeline projection for an agent run."""

    run_id: str
    status: str
    decisions: list[dict[str, Any]]
    subgoals: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]
    evidence_candidates: list[dict[str, Any]]
    human_review_items: list[dict[str, Any]]


class HumanReviewActionRequest(BaseModel):
    """Review action payload for one pending item."""

    model_config = ConfigDict(extra="forbid")

    action: ReviewAction
    reviewer_comment: str | None = None


def set_agent_runtime_for_tests(runtime: GlobalAgentRuntime | None) -> None:
    """Override the runtime used by ``start_agent_run``. Test-only helper."""
    global _agent_runtime
    _agent_runtime = runtime


def reset_agent_run_store_for_tests() -> None:
    """Clear in-memory V21 agent runs. Test-only helper."""
    _agent_runs.clear()
    set_agent_runtime_for_tests(None)


@router.post("", response_model=AgentRunSummary, status_code=status.HTTP_202_ACCEPTED)
async def start_agent_run(request: AgentRunRequest) -> AgentRunSummary:
    """Start a local V21 agent run."""
    if _agent_runtime is None:
        state = AgentPlanner().initialize(
            user_goal=request.goal,
            workflow_kind=request.workflow_kind,
        )
        state.status = "completed"
    else:
        state = _agent_runtime.run(
            request.goal,
            workflow_kind=request.workflow_kind,
            subject=request.subject,
        )
    _agent_runs[state.run_id] = state
    return AgentRunSummary(
        run_id=state.run_id,
        status=state.status,
        timeline_url=f"/agent-runs/{state.run_id}/timeline",
        trace_url=f"/agent-runs/{state.run_id}/trace.json",
    )


@router.get("/{run_id}", response_model=AgentRunState)
async def get_agent_run(run_id: str) -> AgentRunState:
    """Return the current agent run state."""
    return _require_run(run_id)


@router.get("/{run_id}/timeline", response_model=AgentRunTimeline)
async def get_agent_run_timeline(run_id: str) -> AgentRunTimeline:
    """Return a compact UI timeline projection."""
    state = _require_run(run_id)
    return AgentRunTimeline(
        run_id=state.run_id,
        status=state.status,
        decisions=[d.model_dump(mode="json") for d in state.decisions],
        subgoals=[s.model_dump(mode="json") for s in state.subgoals],
        tool_events=[
            event.model_dump(mode="json")
            for trace in state.tool_traces
            for event in trace.tool_events
        ],
        evidence_candidates=list(state.evidence_candidates),
        human_review_items=[
            item.model_dump(mode="json") for item in state.human_review_items
        ],
    )


@router.get("/{run_id}/trace.json", response_model=dict)
async def get_agent_run_trace(run_id: str) -> dict:
    """Return the full redacted, downloadable agent trace."""
    state = _require_run(run_id)
    return redact_obj(state.model_dump(mode="json"))


@router.post(
    "/{run_id}/review-items/{item_id}",
    response_model=HumanReviewItem,
)
async def review_agent_run_item(
    run_id: str,
    item_id: str,
    request: HumanReviewActionRequest,
) -> HumanReviewItem:
    """Approve, reject, or comment on one review item."""
    state = _require_run(run_id)
    item = _find_review_item(state, item_id)
    item.status = {
        "approve": "approved",
        "reject": "rejected",
        "comment": "commented",
    }[request.action]
    item.reviewer_comment = request.reviewer_comment
    item.reviewed_at = _now()
    if item.object_type == "evidence_candidate":
        if request.action == "approve" and item.object_id not in state.accepted_evidence_ids:
            state.accepted_evidence_ids.append(item.object_id)
        if request.action == "reject" and item.object_id in state.accepted_evidence_ids:
            state.accepted_evidence_ids.remove(item.object_id)
    if state.human_review_items and all(
        review.status != "pending" for review in state.human_review_items
    ):
        state.status = "completed"
    _agent_runs[state.run_id] = state
    return item


def _require_run(run_id: str) -> AgentRunState:
    state = _agent_runs.get(run_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="unknown agent run",
        )
    return state


def _find_review_item(state: AgentRunState, item_id: str) -> HumanReviewItem:
    for item in state.human_review_items:
        if item.item_id == item_id:
            return item
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="unknown review item",
    )


__all__ = [
    "AgentRunRequest",
    "AgentRunSummary",
    "AgentRunTimeline",
    "HumanReviewActionRequest",
    "get_agent_run",
    "get_agent_run_timeline",
    "get_agent_run_trace",
    "reset_agent_run_store_for_tests",
    "review_agent_run_item",
    "router",
    "set_agent_runtime_for_tests",
    "start_agent_run",
]
