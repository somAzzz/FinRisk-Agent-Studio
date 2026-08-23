"""V21 local agent-run API routes."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.state import AgentRunState, AgentWorkflowKind, HumanReviewItem, _now
from src.ai.runtime_types import DEFAULT_SYSTEM_PROMPT
from src.api.store_factory import get_agent_run_store
from src.config import AgentRuntimeMode, StoredAgentRuntimeMode
from src.security.redaction import redact_obj

router = APIRouter(prefix="/agent-runs")

ReviewAction = Literal["approve", "reject", "comment"]
AgentRunProvider = Literal["deepseek", "vllm", "sglang"]
AgentRunToolLoopMode = Literal["native", "json_fallback", "auto"]
AgentRunToolScope = Literal["company_research", "finrisk_market", "supply_chain"]

_agent_runtime: GlobalAgentRuntime | None = None
_background_tasks: set[asyncio.Task] = set()


class AgentRunRequest(BaseModel):
    """Request body for starting a V21 agent run."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)
    workflow_kind: AgentWorkflowKind = "generic_research"
    provider: AgentRunProvider = "deepseek"
    # Deprecated: kept for backwards compatibility, ignored by the runtime.
    tool_loop_mode: AgentRunToolLoopMode | None = None
    tool_scope: AgentRunToolScope | None = None
    max_tool_rounds: int = Field(default=4, ge=0, le=10)
    model: str | None = None
    base_url: str | None = None
    demo_mode: bool = False
    cached_mode: bool = False
    subject: dict[str, Any] = Field(default_factory=dict)


class AgentRunSummary(BaseModel):
    """Lightweight response for a newly started agent run."""

    run_id: str
    status: str
    runtime_mode: StoredAgentRuntimeMode
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


class AgentRunResumeRequest(BaseModel):
    """Server-trusted continuation options for an existing conversation."""

    model_config = ConfigDict(extra="forbid")

    goal: str | None = Field(default=None, min_length=1)
    provider: AgentRunProvider = "deepseek"
    # Deprecated: kept for backwards compatibility, ignored by the runtime.
    tool_loop_mode: AgentRunToolLoopMode | None = None
    tool_scope: AgentRunToolScope | None = None
    max_tool_rounds: int = Field(default=4, ge=0, le=10)
    model: str | None = None
    base_url: str | None = None
    subject: dict[str, Any] = Field(default_factory=dict)


def set_agent_runtime_for_tests(runtime: GlobalAgentRuntime | None) -> None:
    """Override the runtime used by ``start_agent_run``. Test-only helper."""
    global _agent_runtime
    _agent_runtime = runtime


def reset_agent_run_store_for_tests() -> None:
    """Clear cached V21 agent-run store. Test-only helper."""
    get_agent_run_store.cache_clear()
    from src.ai.store_factory import reset_agent_message_store_for_tests

    reset_agent_message_store_for_tests()
    set_agent_runtime_for_tests(None)


@router.post("", response_model=AgentRunSummary, status_code=status.HTTP_202_ACCEPTED)
async def start_agent_run(request: AgentRunRequest) -> AgentRunSummary:
    """Start a local V21 agent run."""
    state = AgentRunState(
        user_goal=request.goal,
        workflow_kind=request.workflow_kind,
        status="queued",
        runtime_mode=_current_agent_runtime_mode(),
    )
    await get_agent_run_store().update(state)
    if _background_enabled():
        _schedule(_run_and_store_agent(request, state.run_id))
    else:
        await _run_and_store_agent(request, state.run_id)
    return AgentRunSummary(
        run_id=state.run_id,
        status=state.status,
        runtime_mode=state.runtime_mode,
        timeline_url=f"/agent-runs/{state.run_id}/timeline",
        trace_url=f"/agent-runs/{state.run_id}/trace.json",
    )


@router.get("", response_model=list[AgentRunSummary])
async def list_agent_runs(limit: int = 20) -> list[AgentRunSummary]:
    """Return recent local V21 agent runs."""
    states = await get_agent_run_store().list_recent(limit)
    return [
        AgentRunSummary(
            run_id=state.run_id,
            status=state.status,
            runtime_mode=state.runtime_mode,
            timeline_url=f"/agent-runs/{state.run_id}/timeline",
            trace_url=f"/agent-runs/{state.run_id}/trace.json",
        )
        for state in states[:limit]
    ]


@router.get("/{run_id}", response_model=AgentRunState)
async def get_agent_run(run_id: str) -> AgentRunState:
    """Return the current agent run state."""
    return await _require_run(run_id)


@router.get("/{run_id}/timeline", response_model=AgentRunTimeline)
async def get_agent_run_timeline(run_id: str) -> AgentRunTimeline:
    """Return a compact UI timeline projection."""
    state = await _require_run(run_id)
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
    state = await _require_run(run_id)
    return redact_obj(state.model_dump(mode="json"))


@router.post(
    "/{run_id}/resume",
    response_model=AgentRunSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_agent_run(
    run_id: str,
    request: AgentRunResumeRequest,
) -> AgentRunSummary:
    """Resume trusted server-side history under a new run ID."""
    parent = await _require_run(run_id)
    state = AgentRunState(
        user_goal=request.goal or parent.user_goal,
        workflow_kind=parent.workflow_kind,
        status="queued",
        conversation_id=parent.conversation_id,
        parent_run_id=parent.run_id,
        runtime_mode=_current_agent_runtime_mode(),
    )
    await get_agent_run_store().update(state)
    run_request = AgentRunRequest(
        goal=state.user_goal,
        workflow_kind=state.workflow_kind,
        provider=request.provider,
        tool_loop_mode=request.tool_loop_mode,
        tool_scope=request.tool_scope,
        max_tool_rounds=request.max_tool_rounds,
        model=request.model,
        base_url=request.base_url,
        subject=request.subject,
    )
    if _background_enabled():
        _schedule(_run_and_store_agent(run_request, state.run_id))
    else:
        await _run_and_store_agent(run_request, state.run_id)
    return AgentRunSummary(
        run_id=state.run_id,
        status=state.status,
        runtime_mode=state.runtime_mode,
        timeline_url=f"/agent-runs/{state.run_id}/timeline",
        trace_url=f"/agent-runs/{state.run_id}/trace.json",
    )


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
    state = await _require_run(run_id)
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
    await get_agent_run_store().update(state)
    return item


@router.post(
    "/{run_id}/evidence-candidates/{candidate_id}",
    response_model=dict,
)
async def review_agent_evidence_candidate(
    run_id: str,
    candidate_id: str,
    request: HumanReviewActionRequest,
) -> dict[str, Any]:
    """Approve, reject, or comment on one evidence candidate directly."""
    state = await _require_run(run_id)
    candidate = _find_evidence_candidate(state, candidate_id)
    resolved_id = str(candidate.get("candidate_id") or candidate.get("evidence_id"))
    if request.action == "approve":
        candidate["status"] = "accepted"
        candidate["rejection_reason"] = None
        if resolved_id not in state.accepted_evidence_ids:
            state.accepted_evidence_ids.append(resolved_id)
    elif request.action == "reject":
        candidate["status"] = "rejected"
        candidate["rejection_reason"] = (
            request.reviewer_comment or "Rejected by reviewer."
        )
        if resolved_id in state.accepted_evidence_ids:
            state.accepted_evidence_ids.remove(resolved_id)
    else:
        candidate["reviewer_comment"] = request.reviewer_comment

    if not any(
        c.get("status") == "needs_review" for c in state.evidence_candidates
    ) and (
        not state.human_review_items
        or all(review.status != "pending" for review in state.human_review_items)
    ):
        state.status = "completed"
    state.updated_at = _now()
    await get_agent_run_store().update(state)
    return candidate


async def _require_run(run_id: str) -> AgentRunState:
    state = await get_agent_run_store().get(run_id)
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


def _find_evidence_candidate(
    state: AgentRunState,
    candidate_id: str,
) -> dict[str, Any]:
    for candidate in state.evidence_candidates:
        if candidate.get("candidate_id") == candidate_id:
            return candidate
        if candidate.get("evidence_id") == candidate_id:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="unknown evidence candidate",
    )


def build_agent_runtime(request: AgentRunRequest) -> GlobalAgentRuntime:
    """Build the real V21 runtime used by the local agent-run API."""
    return _build_pydantic_agent_runtime(request)


def _build_pydantic_agent_runtime(request: AgentRunRequest) -> GlobalAgentRuntime:
    """Build the primary Pydantic AI subgoal path behind the feature flag."""
    from src.agents.planner import AgentPlanner
    from src.agents.state import AgentBudget
    from src.ai.deps import (
        AgentDeps,
        AgentPermissions,
        AgentServices,
        AgentSubject,
    )
    from src.ai.model_factory import (
        build_agent_model,
        resolve_agent_model_config,
    )
    from src.ai.planner_adapter import PydanticAIPlanner
    from src.ai.runtime_adapter import PydanticAIRuntimeAdapter
    from src.ai.store_factory import get_agent_run_recorder
    from src.config import get_settings
    from src.schemas.llm_config import LLMRunConfig
    from src.tools.catalog import build_project_tool_catalog

    settings = get_settings()
    run_config = LLMRunConfig(
        provider=request.provider,
        base_url=request.base_url,
        model=request.model,
    )
    model = build_agent_model(
        resolve_agent_model_config(
            run_config,
            settings=settings,
        )
    )
    recorder = get_agent_run_recorder()
    planner_catalog = build_project_tool_catalog(llm_config=run_config, scope=None)
    planner = PydanticAIPlanner(
        model=model,
        settings=settings,
        tool_catalog=planner_catalog,
        services=AgentServices(
            tool_catalog=planner_catalog,
            message_recorder=recorder,
        ),
    )

    def factory(
        tool_scope: str,
        subgoal: Any,
        run_state: AgentRunState,
    ) -> PydanticAIRuntimeAdapter:
        selected_scope = request.tool_scope or _coerce_tool_scope(tool_scope)
        catalog = build_project_tool_catalog(
            llm_config=run_config,
            scope=selected_scope,
        )
        subject = request.subject
        deps = AgentDeps(
            run_id=f"{run_state.run_id}:{subgoal.subgoal_id}",
            conversation_id=run_state.conversation_id,
            load_message_history=True,
            settings=settings,
            subject=AgentSubject(
                ticker=subject.get("ticker"),
                company_name=subject.get("company_name"),
                product_name=subject.get("product_name"),
                metadata=subject,
            ),
            permissions=AgentPermissions(
                tool_scopes=frozenset({selected_scope}),
                allow_interactive=False,
                allow_write=False,
            ),
            budget=AgentBudget(
                max_subgoals=1,
                max_tool_rounds_per_subgoal=request.max_tool_rounds,
            ),
            services=AgentServices(
                tool_catalog=catalog,
                message_recorder=recorder,
            ),
        )
        return PydanticAIRuntimeAdapter(
            model=model,
            deps=deps,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
        )

    return GlobalAgentRuntime(
        planner=AgentPlanner(llm_planner=planner),
        subgoal_runtime_factory=factory,
    )


async def _run_and_store_agent(request: AgentRunRequest, run_id: str) -> None:
    """Run the synchronous agent runtime off the FastAPI event loop."""
    store = get_agent_run_store()
    try:
        state = await store.get(run_id)
        if state is None:
            return
        state.status = "running"
        state.updated_at = _now()
        await store.update(state)
        runtime = _agent_runtime or build_agent_runtime(request)
        conversation_id = state.conversation_id
        parent_run_id = state.parent_run_id
        runtime_mode = state.runtime_mode
        state = await asyncio.to_thread(
            runtime.run,
            request.goal,
            workflow_kind=request.workflow_kind,
            subject=request.subject,
            run_id=run_id,
            conversation_id=conversation_id,
        )
        state.run_id = run_id
        state.conversation_id = conversation_id
        state.parent_run_id = parent_run_id
        state.runtime_mode = runtime_mode
    except Exception as exc:
        state = await store.get(run_id)
        if state is None:
            state = AgentRunState(
                run_id=run_id,
                user_goal=request.goal,
                workflow_kind=request.workflow_kind,
                runtime_mode=_current_agent_runtime_mode(),
            )
        state.status = "failed"
        state.fallback_events.append(f"agent_run failed: {type(exc).__name__}: {exc}")
    state.updated_at = _now()
    await store.update(state)


def _schedule(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _background_enabled() -> bool:
    return os.environ.get("FINRISK_SKIP_BACKGROUND") != "1"


def _current_agent_runtime_mode() -> AgentRuntimeMode:
    from src.config import get_settings

    return get_settings().agent_runtime_mode


def _coerce_tool_scope(tool_scope: str) -> AgentRunToolScope:
    if tool_scope in {"company_research", "finrisk_market", "supply_chain"}:
        return tool_scope  # type: ignore[return-value]
    return "company_research"


__all__ = [
    "AgentRunRequest",
    "AgentRunResumeRequest",
    "AgentRunSummary",
    "AgentRunTimeline",
    "HumanReviewActionRequest",
    "build_agent_runtime",
    "get_agent_run",
    "get_agent_run_timeline",
    "get_agent_run_trace",
    "list_agent_runs",
    "reset_agent_run_store_for_tests",
    "resume_agent_run",
    "review_agent_evidence_candidate",
    "review_agent_run_item",
    "router",
    "set_agent_runtime_for_tests",
    "start_agent_run",
]
