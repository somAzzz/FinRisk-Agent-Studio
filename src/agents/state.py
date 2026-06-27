"""Runtime state containers shared across agents."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence
from src.schemas.relations import Relation
from src.schemas.tool_trace import ToolLoopTrace

AgentRunStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "needs_review",
]

AgentSubgoalStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
    "needs_review",
]

AgentWorkflowKind = Literal[
    "finrisk",
    "supply_chain",
    "company_research",
    "generic_research",
]

AgentDecisionType = Literal[
    "plan",
    "call_tools",
    "accept_evidence",
    "ask_review",
    "fallback",
    "stop",
]

AgentStopReason = Literal[
    "enough_evidence",
    "budget_exhausted",
    "tool_failures",
    "low_confidence",
    "human_review_required",
    "user_cancelled",
]


def _now() -> datetime:
    return datetime.now(tz=UTC)


class ToolCall(BaseModel):
    """A single recorded invocation of a tool during a runtime step."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any]
    result_summary: str | None = None
    success: bool = True
    created_at: datetime


class AgentState(BaseModel):
    """Mutable, JSON-serializable state passed between agents during a run."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    ticker: str | None = None
    company_name: str | None = None
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    tool_history: list[ToolCall] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    max_steps: int = 10
    current_step: int = 0


class AgentBudget(BaseModel):
    """Cross-subgoal budget for a V21 agent run."""

    model_config = ConfigDict(extra="forbid")

    max_subgoals: int = Field(default=8, ge=1)
    max_tool_rounds_per_subgoal: int = Field(default=4, ge=0)
    max_total_tool_calls: int = Field(default=20, ge=0)
    max_total_fetch_pages: int = Field(default=10, ge=0)
    max_total_runtime_seconds: int = Field(default=300, ge=1)
    max_total_tool_result_chars: int = Field(default=40000, ge=0)


class AgentSubgoal(BaseModel):
    """One planner-created objective in a larger agent run."""

    model_config = ConfigDict(extra="forbid")

    subgoal_id: str = Field(default_factory=lambda: f"sg-{uuid.uuid4().hex[:8]}")
    parent_subgoal_id: str | None = None
    objective: str
    status: AgentSubgoalStatus = "pending"
    tool_scope: str = "company_research"
    required_evidence_types: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    attempt_count: int = Field(default=0, ge=0)
    depends_on: list[str] = Field(default_factory=list)


class AgentDecision(BaseModel):
    """One auditable planner decision."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:8]}")
    subgoal_id: str | None = None
    decision_type: AgentDecisionType
    rationale: str
    selected_tool_scope: str | None = None
    selected_tools: list[str] = Field(default_factory=list)
    next_subgoals: list[AgentSubgoal] = Field(default_factory=list)
    stop_reason: AgentStopReason | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def _stop_requires_reason(self) -> AgentDecision:
        if self.decision_type == "stop" and self.stop_reason is None:
            raise ValueError("stop decisions must include stop_reason")
        if self.decision_type != "stop" and self.stop_reason is not None:
            raise ValueError("stop_reason is only valid for stop decisions")
        return self

    @classmethod
    def stop(
        cls,
        *,
        rationale: str,
        stop_reason: AgentStopReason,
        confidence: float = 0.5,
    ) -> AgentDecision:
        return cls(
            decision_type="stop",
            rationale=rationale,
            stop_reason=stop_reason,
            confidence=confidence,
        )


class AgentRunTrace(BaseModel):
    """Compact trace row for V21 agent runtime events."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(default_factory=lambda: f"atr-{uuid.uuid4().hex[:8]}")
    event_type: str
    message: str
    subgoal_id: str | None = None
    created_at: datetime = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunState(BaseModel):
    """Global V21 agent state across planner decisions and subgoals."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: f"agent-{uuid.uuid4().hex[:12]}")
    user_goal: str
    workflow_kind: AgentWorkflowKind = "generic_research"
    status: AgentRunStatus = "queued"
    subgoals: list[AgentSubgoal] = Field(default_factory=list)
    decisions: list[AgentDecision] = Field(default_factory=list)
    tool_traces: list[ToolLoopTrace] = Field(default_factory=list)
    evidence_candidates: list[dict[str, Any]] = Field(default_factory=list)
    accepted_evidence_ids: list[str] = Field(default_factory=list)
    context_pack: dict[str, Any] | None = None
    fallback_events: list[str] = Field(default_factory=list)
    human_review_items: list[dict[str, Any]] = Field(default_factory=list)
    budget: AgentBudget = Field(default_factory=AgentBudget)
    trace: list[AgentRunTrace] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def append_decision(self, decision: AgentDecision) -> None:
        """Record a planner decision and merge any newly proposed subgoals."""
        self.decisions.append(decision)
        existing = {subgoal.subgoal_id for subgoal in self.subgoals}
        for subgoal in decision.next_subgoals:
            if subgoal.subgoal_id in existing:
                continue
            self.subgoals.append(subgoal)
            existing.add(subgoal.subgoal_id)
        self.updated_at = _now()

    def next_pending_subgoal(self) -> AgentSubgoal | None:
        """Return the first pending subgoal whose dependencies are complete."""
        completed = {
            subgoal.subgoal_id
            for subgoal in self.subgoals
            if subgoal.status == "completed"
        }
        for subgoal in self.subgoals:
            if subgoal.status != "pending":
                continue
            if all(dep in completed for dep in subgoal.depends_on):
                return subgoal
        return None


__all__ = [
    "AgentBudget",
    "AgentDecision",
    "AgentDecisionType",
    "AgentRunState",
    "AgentRunStatus",
    "AgentRunTrace",
    "AgentState",
    "AgentStopReason",
    "AgentSubgoal",
    "AgentSubgoalStatus",
    "AgentWorkflowKind",
    "ToolCall",
]
