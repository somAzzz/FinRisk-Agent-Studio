"""Global V21 agent runtime with planner-driven subgoal execution."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from src.agents.context import AgentContextBuilder
from src.agents.llm_runtime import LLMToolRunResult
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


class SubgoalRuntime(Protocol):
    """Runtime capable of executing one subgoal objective."""

    def run(self, goal: str) -> LLMToolRunResult:
        """Execute ``goal`` and return tool-loop results."""


SubgoalRuntimeFactory = Callable[[str, AgentSubgoal], SubgoalRuntime]


class GlobalAgentRuntime:
    """Coordinate planner decisions, subgoal tool runs, and evidence ingestion."""

    def __init__(
        self,
        *,
        planner: AgentPlanner | None = None,
        subgoal_runtime_factory: SubgoalRuntimeFactory,
        evidence_normalizer: EvidenceCandidateNormalizer | None = None,
        context_builder: AgentContextBuilder | None = None,
    ) -> None:
        self.planner = planner or AgentPlanner()
        self.subgoal_runtime_factory = subgoal_runtime_factory
        self.evidence_normalizer = evidence_normalizer or EvidenceCandidateNormalizer()
        self.context_builder = context_builder

    def run(
        self,
        user_goal: str,
        *,
        workflow_kind: AgentWorkflowKind = "generic_research",
        budget: AgentBudget | None = None,
        subject: dict | None = None,
    ) -> AgentRunState:
        """Run an agent task until stop, review, failure, or budget exhaustion."""
        state = self.planner.initialize(
            user_goal=user_goal,
            workflow_kind=workflow_kind,
        )
        if self.context_builder is not None:
            context_pack = self.context_builder.build(
                run_id=state.run_id,
                user_goal=user_goal,
                workflow_kind=workflow_kind,
                subject=subject,
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
        if budget is not None:
            state.budget = budget
        state.status = "running"
        started = time.perf_counter()
        executed_subgoals = 0
        tool_calls = 0

        while state.status == "running":
            if executed_subgoals >= state.budget.max_subgoals:
                self._stop(state, "budget_exhausted", "Subgoal budget exhausted.")
                break
            if time.perf_counter() - started > state.budget.max_total_runtime_seconds:
                self._stop(state, "budget_exhausted", "Runtime budget exhausted.")
                break
            decision = self.planner.decide(state)
            state.append_decision(decision)
            if decision.decision_type == "stop":
                state.status = "completed"
                break
            if decision.decision_type != "call_tools":
                self._stop(state, "low_confidence", "Planner did not select tools.")
                break
            subgoal = state.next_pending_subgoal()
            if subgoal is None:
                self._stop(state, "enough_evidence", "No pending subgoals remain.")
                break
            subgoal.status = "running"
            try:
                result = self.subgoal_runtime_factory(subgoal.tool_scope, subgoal).run(
                    subgoal.objective
                )
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
                self._stop(state, "tool_failures", "Subgoal runtime failed.")
                break
            executed_subgoals += 1
            tool_calls += len(result.tool_events)
            state.tool_traces.append(
                ToolLoopTrace(
                    mode=result.mode,
                    tool_events=result.tool_events,
                    budget_usage=result.budget_usage,
                )
            )
            candidates = self.evidence_normalizer.normalize_events(
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
            if tool_calls >= state.budget.max_total_tool_calls:
                self._stop(state, "budget_exhausted", "Tool-call budget exhausted.")
                break
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
                self._stop(
                    state,
                    "human_review_required",
                    "Subgoal produced no accepted evidence.",
                )
                state.status = "needs_review"
                break

        return state

    @staticmethod
    def _stop(
        state: AgentRunState,
        stop_reason: AgentStopReason,
        rationale: str,
    ) -> None:
        state.append_decision(
            AgentDecision.stop(
                rationale=rationale,
                stop_reason=stop_reason,
            )
        )
        if state.status == "running":
            state.status = "completed"


__all__ = [
    "GlobalAgentRuntime",
    "SubgoalRuntime",
    "SubgoalRuntimeFactory",
]
