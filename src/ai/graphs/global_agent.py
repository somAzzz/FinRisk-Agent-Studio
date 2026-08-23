"""Pydantic Graph control flow for planner-driven global Agent runs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from pydantic_graph import Graph, GraphBuilder, StepContext

from src.agents.context import AgentContextBuilder
from src.agents.planner import AgentPlanner
from src.agents.state import (
    AgentBudget,
    AgentDecision,
    AgentRunState,
    AgentRunTrace,
    AgentStopReason,
    AgentSubgoal,
    AgentWorkflowKind,
    HumanReviewItem,
)
from src.evidence import EvidenceCandidateNormalizer
from src.schemas.tool_trace import ToolLoopTrace


@dataclass(slots=True)
class GlobalAgentGraphInput:
    user_goal: str
    workflow_kind: AgentWorkflowKind
    budget: AgentBudget | None = None
    subject: dict[str, Any] | None = None
    run_id: str | None = None
    conversation_id: str | None = None


@dataclass(slots=True)
class GlobalAgentGraphState:
    run_state: AgentRunState | None = None
    started_at: float = 0.0
    executed_subgoals: int = 0
    tool_calls: int = 0
    active_subgoal_id: str | None = None


@dataclass(slots=True)
class GlobalAgentGraphDeps:
    planner: AgentPlanner
    subgoal_runtime_factory: Any
    evidence_normalizer: EvidenceCandidateNormalizer
    context_builder: AgentContextBuilder | None = None


def build_global_agent_graph() -> Graph[
    GlobalAgentGraphState,
    GlobalAgentGraphDeps,
    GlobalAgentGraphInput,
    AgentRunState,
]:
    """Build the bounded planner -> subgoal -> planner execution graph."""
    builder = GraphBuilder(
        name="global-agent-runtime",
        state_type=GlobalAgentGraphState,
        deps_type=GlobalAgentGraphDeps,
        input_type=GlobalAgentGraphInput,
        output_type=AgentRunState,
    )

    @builder.step(node_id="initialize")
    async def initialize(
        ctx: StepContext[
            GlobalAgentGraphState,
            GlobalAgentGraphDeps,
            GlobalAgentGraphInput,
        ],
    ) -> None:
        inputs = ctx.inputs
        state = ctx.deps.planner.initialize(
            user_goal=inputs.user_goal,
            workflow_kind=inputs.workflow_kind,
        )
        initialized_run_id = state.run_id
        if inputs.run_id is not None:
            state.run_id = inputs.run_id
            if state.conversation_id == initialized_run_id:
                state.conversation_id = inputs.run_id
        if inputs.conversation_id is not None:
            state.conversation_id = inputs.conversation_id
        if ctx.deps.context_builder is not None:
            context_pack = ctx.deps.context_builder.build(
                run_id=state.run_id,
                user_goal=inputs.user_goal,
                workflow_kind=inputs.workflow_kind,
                subject=inputs.subject,
            )
            state.context_pack = context_pack.model_dump(mode="json")
            state.trace.append(
                AgentRunTrace(
                    event_type="context_pack_selected",
                    message=(
                        f"selected {len(context_pack.selected_memory_ids)} "
                        "memory item(s) for agent context"
                    ),
                    metadata={
                        "context_pack_id": context_pack.context_pack_id,
                        "selected_memory_ids": context_pack.selected_memory_ids,
                        "rejected_memory_ids": context_pack.rejected_memory_ids,
                    },
                )
            )
        if inputs.budget is not None:
            state.budget = inputs.budget
        state.status = "running"
        ctx.state.run_state = state
        ctx.state.started_at = time.perf_counter()

    @builder.step(node_id="plan_next")
    async def plan_next(  # noqa: PLR0911
        ctx: StepContext[GlobalAgentGraphState, GlobalAgentGraphDeps, None],
    ) -> str:
        state = _require_state(ctx.state)
        if state.status != "running":
            return "finish"
        if ctx.state.executed_subgoals >= state.budget.max_subgoals:
            _stop(state, "budget_exhausted", "Subgoal budget exhausted.")
            return "finish"
        if (
            time.perf_counter() - ctx.state.started_at
            > state.budget.max_total_runtime_seconds
        ):
            _stop(state, "budget_exhausted", "Runtime budget exhausted.")
            return "finish"

        decision = ctx.deps.planner.decide(state)
        state.append_decision(decision)
        if decision.decision_type == "stop":
            state.status = "completed"
            return "finish"
        if decision.decision_type != "call_tools":
            _stop(state, "low_confidence", "Planner did not select tools.")
            return "finish"
        subgoal = state.next_pending_subgoal()
        if subgoal is None:
            _stop(state, "enough_evidence", "No pending subgoals remain.")
            return "finish"
        subgoal.status = "running"
        ctx.state.active_subgoal_id = subgoal.subgoal_id
        return "execute"

    @builder.step(node_id="execute_subgoal")
    async def execute_subgoal(
        ctx: StepContext[GlobalAgentGraphState, GlobalAgentGraphDeps, str],
    ) -> None:
        state = _require_state(ctx.state)
        subgoal = next(
            (
                item
                for item in state.subgoals
                if item.subgoal_id == ctx.state.active_subgoal_id
            ),
            None,
        )
        if subgoal is None:
            _stop(state, "enough_evidence", "No pending subgoals remain.")
            return
        try:
            from src.agents.global_runtime import _create_subgoal_runtime

            runtime = _create_subgoal_runtime(
                ctx.deps.subgoal_runtime_factory,
                subgoal.tool_scope,
                subgoal,
                state,
            )
            result = runtime.run(subgoal.objective)
        except Exception as exc:
            subgoal.status = "failed"
            state.fallback_events.append(
                f"global_agent_runtime:subgoal {subgoal.subgoal_id} failed: {exc}"
            )
            state.trace.append(
                AgentRunTrace(
                    event_type="subgoal_failed",
                    message=str(exc),
                    subgoal_id=subgoal.subgoal_id,
                )
            )
            _stop(state, "tool_failures", "Subgoal runtime failed.")
            state.status = "failed"
            return

        ctx.state.executed_subgoals += 1
        ctx.state.tool_calls += len(result.tool_events)
        state.tool_traces.append(
            ToolLoopTrace(
                mode=result.mode,
                tool_events=result.tool_events,
                budget_usage=result.budget_usage,
            )
        )
        if not result.tool_events:
            _mark_missing_tool_evidence(
                state,
                subgoal,
                result.final_answer,
                result.mode,
            )
            ctx.state.active_subgoal_id = None
            return

        candidates = ctx.deps.evidence_normalizer.normalize_events(
            result.tool_events,
            related_subgoal_id=subgoal.subgoal_id,
            related_text=subgoal.objective,
        )
        state.evidence_candidates.extend(
            candidate.model_dump(mode="json") for candidate in candidates
        )
        state.accepted_evidence_ids.extend(
            candidate.candidate_id
            for candidate in candidates
            if candidate.status == "accepted"
        )
        subgoal.status = (
            "completed"
            if any(candidate.status == "accepted" for candidate in candidates)
            else "needs_review"
        )
        state.trace.append(
            AgentRunTrace(
                event_type="subgoal_completed",
                message=(
                    f"produced {len(candidates)} evidence candidate(s); "
                    f"{len(state.accepted_evidence_ids)} accepted total"
                ),
                subgoal_id=subgoal.subgoal_id,
            )
        )
        if ctx.state.tool_calls >= state.budget.max_total_tool_calls:
            _stop(state, "budget_exhausted", "Tool-call budget exhausted.")
            return
        if subgoal.status == "needs_review":
            reviewed_candidate = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.status == "needs_review"
                ),
                candidates[0] if candidates else None,
            )
            if reviewed_candidate is not None:
                state.human_review_items.append(
                    HumanReviewItem(
                        run_id=state.run_id,
                        subgoal_id=subgoal.subgoal_id,
                        object_type="evidence_candidate",
                        object_id=reviewed_candidate.candidate_id,
                        reason=(
                            reviewed_candidate.rejection_reason
                            or "Subgoal produced evidence requiring review."
                        ),
                        suggested_action="inspect_source",
                    )
                )
            _stop(
                state,
                "human_review_required",
                "Subgoal produced no accepted evidence.",
            )
            state.status = "needs_review"
        ctx.state.active_subgoal_id = None

    @builder.step(node_id="finish")
    async def finish(
        ctx: StepContext[GlobalAgentGraphState, GlobalAgentGraphDeps, str],
    ) -> AgentRunState:
        return _require_state(ctx.state)

    route = builder.decision(
        node_id="route_after_plan",
        note="Execute a subgoal or finish the bounded run.",
    )
    route = route.branch(
        builder.match(str, matches=lambda value: value == "execute").to(
            execute_subgoal
        )
    )
    route = route.branch(
        builder.match(str, matches=lambda value: value == "finish").to(finish)
    )

    builder.add_edge(builder.start_node, initialize)
    builder.add_edge(initialize, plan_next)
    builder.add_edge(plan_next, route)
    builder.add_edge(execute_subgoal, plan_next)
    builder.add_edge(finish, builder.end_node)
    return builder.build()


async def run_global_agent_graph(
    inputs: GlobalAgentGraphInput,
    *,
    deps: GlobalAgentGraphDeps,
) -> AgentRunState:
    """Execute one global Agent run through Pydantic Graph."""
    return await build_global_agent_graph().run(
        state=GlobalAgentGraphState(),
        deps=deps,
        inputs=inputs,
    )


def _mark_missing_tool_evidence(
    state: AgentRunState,
    subgoal: AgentSubgoal,
    final_answer: str,
    mode: str,
) -> None:
    subgoal.status = "needs_review"
    subgoal_id = subgoal.subgoal_id
    state.fallback_events.append(
        f"global_agent_runtime:subgoal {subgoal_id} produced no tool evidence"
    )
    state.trace.append(
        AgentRunTrace(
            event_type="subgoal_no_tool_evidence",
            message="Subgoal runtime returned without executing any tools.",
            subgoal_id=subgoal_id,
            metadata={
                "mode": mode,
                "final_answer_chars": len(final_answer),
            },
        )
    )
    state.human_review_items.append(
        HumanReviewItem(
            run_id=state.run_id,
            subgoal_id=subgoal_id,
            object_type="report_claim",
            object_id=subgoal_id,
            reason="Subgoal completed without tool-backed evidence.",
            suggested_action="inspect_source",
        )
    )
    _stop(
        state,
        "human_review_required",
        "Subgoal produced no tool-backed evidence.",
    )
    state.status = "needs_review"


def _stop(
    state: AgentRunState,
    stop_reason: AgentStopReason,
    rationale: str,
) -> None:
    state.append_decision(
        AgentDecision.stop(rationale=rationale, stop_reason=stop_reason)
    )
    if state.status == "running":
        state.status = "completed"


def _require_state(state: GlobalAgentGraphState) -> AgentRunState:
    if state.run_state is None:
        raise RuntimeError("Global Agent graph was not initialized")
    return state.run_state


__all__ = [
    "GlobalAgentGraphDeps",
    "GlobalAgentGraphInput",
    "GlobalAgentGraphState",
    "build_global_agent_graph",
    "run_global_agent_graph",
]
