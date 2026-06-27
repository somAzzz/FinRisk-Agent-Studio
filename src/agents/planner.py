"""Rule-based planner that turns an ``AgentState`` into an ``AgentPlan``."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agents.state import (
    AgentDecision,
    AgentRunState,
    AgentState,
    AgentSubgoal,
    AgentWorkflowKind,
)

PlanStepAction = Literal[
    "fetch_filing",
    "fetch_transcript",
    "web_search",
    "extract_entities",
    "extract_relations",
    "write_graph",
    "analyze_risk",
    "analyze_sentiment",
    "discover_opportunity",
    "finish",
]


class PlanStep(BaseModel):
    """A single planned step to be executed by the runtime."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    action: PlanStepAction
    reason: str
    inputs: dict[str, Any] = Field(default_factory=dict)


class AgentPlan(BaseModel):
    """An ordered list of plan steps plus a flag for missing inputs."""

    model_config = ConfigDict(extra="forbid")

    steps: list[PlanStep]
    needs_more_info: bool = False


class PlannerAgent:
    """A small rule-based planner.

    The planner inspects the current ``AgentState`` and emits the next
    concrete steps. It is intentionally deterministic and does not call any
    LLM, so the runtime is testable without external services.
    """

    name: str = "planner"

    def run(self, state: AgentState) -> AgentState:
        """Run the planner and store the plan in ``state.notes``.

        The planner itself is side-effect free on the analytical fields of
        ``state``; it only annotates ``state.notes`` with the generated plan
        for observability. The actual plan is returned from
        :meth:`plan` and consumed by the runtime.
        """
        plan = self.plan(state)
        state.notes.append(f"planner: produced {len(plan.steps)} step(s)")
        return state

    def plan(self, state: AgentState) -> AgentPlan:
        """Build an :class:`AgentPlan` from the current ``state``."""
        steps: list[PlanStep] = []
        step_index = 0

        def next_id() -> str:
            nonlocal step_index
            step_index += 1
            return f"step_{step_index}"

        needs_more_info = False

        filing_types = {"edgar_corpus", "sec_filing", "sec_xbrl"}
        web_types = {"web", "browser"}

        def _ev_source_type(ev: Any) -> str | None:
            """Return ``ev.source_type`` whether ``ev`` is dict or Evidence."""
            if isinstance(ev, dict):
                return ev.get("source_type")
            return getattr(ev, "source_type", None)

        has_filing_evidence = any(
            _ev_source_type(ev) in filing_types for ev in state.evidence
        )
        has_transcript_evidence = any(
            _ev_source_type(ev) == "transcript" for ev in state.evidence
        )
        has_web_evidence = any(
            _ev_source_type(ev) in web_types for ev in state.evidence
        )

        # 1. Need a filing? -> fetch_filing
        if state.ticker and not has_filing_evidence:
            needs_more_info = True
            steps.append(
                PlanStep(
                    step_id=next_id(),
                    action="fetch_filing",
                    reason="Ticker provided but no filing evidence present.",
                    inputs={"ticker": state.ticker},
                )
            )

        # 2. Have a filing but no entities? -> extract_entities
        if has_filing_evidence and not state.entities:
            steps.append(
                PlanStep(
                    step_id=next_id(),
                    action="extract_entities",
                    reason="Filing evidence available but no entities extracted.",
                    inputs={},
                )
            )

        # 3. Have entities but no relations? -> extract_relations
        if state.entities and not state.relations:
            steps.append(
                PlanStep(
                    step_id=next_id(),
                    action="extract_relations",
                    reason="Entities available but no relations extracted.",
                    inputs={},
                )
            )

        # 4. Have relations but no graph artifacts? -> write_graph
        if state.relations and not _has_graph_artifact(state):
            steps.append(
                PlanStep(
                    step_id=next_id(),
                    action="write_graph",
                    reason="Relations available but graph not yet written.",
                    inputs={},
                )
            )

        # 5. No transcript yet and one is useful for the goal? -> fetch_transcript
        goal_lc = state.goal.lower()
        wants_transcript = any(
            token in goal_lc
            for token in ("earnings", "transcript", "call", "guidance")
        )
        if wants_transcript and not has_transcript_evidence and state.ticker:
            steps.append(
                PlanStep(
                    step_id=next_id(),
                    action="fetch_transcript",
                    reason="Goal hints at earnings/transcript and none present.",
                    inputs={"ticker": state.ticker},
                )
            )

        # 6. Web search fallback if we have no web evidence and nothing else to do
        if not steps and not has_web_evidence:
            steps.append(
                PlanStep(
                    step_id=next_id(),
                    action="web_search",
                    reason="No evidence collected yet; running a web search.",
                    inputs={"query": state.goal},
                )
            )

        # Always finish with discover_opportunity then finish.
        steps.append(
            PlanStep(
                step_id=next_id(),
                action="discover_opportunity",
                reason="Synthesize opportunities from the collected context.",
                inputs={},
            )
        )
        steps.append(
            PlanStep(
                step_id=next_id(),
                action="finish",
                reason="Plan complete.",
                inputs={},
            )
        )

        return AgentPlan(steps=steps, needs_more_info=needs_more_info)


def _has_graph_artifact(state: AgentState) -> bool:
    """Return True if a previous ``write_graph`` step was recorded."""
    return any("write_graph" in note for note in state.notes)


PlannerOutput = dict[str, Any] | str


class AgentPlanner:
    """V21 planner that emits structured agent decisions.

    The planner accepts an optional callable that can provide an LLM-produced
    structured plan. If parsing or validation fails, it falls back to a small
    deterministic plan so agent runs remain testable offline.
    """

    name = "agent_planner"

    def __init__(
        self,
        *,
        available_tool_scopes: set[str] | None = None,
        llm_planner: Any | None = None,
    ) -> None:
        self.available_tool_scopes = available_tool_scopes or {
            "company_research",
            "finrisk_market",
            "supply_chain",
        }
        self.llm_planner = llm_planner

    def decide(self, state: AgentRunState) -> AgentDecision:
        """Return the next structured decision for ``state``."""
        if self.llm_planner is not None:
            try:
                return self._parse_and_validate(self.llm_planner(state))
            except Exception as exc:
                state.fallback_events.append(
                    f"agent_planner:structured planner fallback: {type(exc).__name__}: {exc}"
                )
        return self._deterministic_decision(state)

    def initialize(
        self,
        *,
        user_goal: str,
        workflow_kind: AgentWorkflowKind = "generic_research",
    ) -> AgentRunState:
        """Create an initial run state and append the first plan decision."""
        state = AgentRunState(user_goal=user_goal, workflow_kind=workflow_kind)
        state.append_decision(self._deterministic_decision(state))
        return state

    def _parse_and_validate(self, raw: PlannerOutput) -> AgentDecision:
        if isinstance(raw, str):
            payload = json.loads(raw)
        else:
            payload = raw
        decision = AgentDecision.model_validate(payload)
        self._validate_decision(decision)
        return decision

    def _validate_decision(self, decision: AgentDecision) -> None:
        scopes = set()
        if decision.selected_tool_scope:
            scopes.add(decision.selected_tool_scope)
        scopes.update(subgoal.tool_scope for subgoal in decision.next_subgoals)
        invalid = sorted(scope for scope in scopes if scope not in self.available_tool_scopes)
        if invalid:
            raise ValueError(f"unknown tool scope(s): {', '.join(invalid)}")

    def _deterministic_decision(self, state: AgentRunState) -> AgentDecision:
        pending = state.next_pending_subgoal()
        if pending is not None:
            return AgentDecision(
                subgoal_id=pending.subgoal_id,
                decision_type="call_tools",
                rationale=f"Run pending subgoal: {pending.objective}",
                selected_tool_scope=pending.tool_scope,
                confidence=0.7,
            )
        if state.subgoals:
            return AgentDecision.stop(
                rationale="No pending subgoals remain.",
                stop_reason="enough_evidence",
                confidence=0.6,
            )
        return AgentDecision(
            decision_type="plan",
            rationale=f"Create initial {state.workflow_kind} research subgoals.",
            next_subgoals=_default_subgoals(
                user_goal=state.user_goal,
                workflow_kind=state.workflow_kind,
            ),
            confidence=0.6,
        )


def _default_subgoals(
    *,
    user_goal: str,
    workflow_kind: AgentWorkflowKind,
) -> list[AgentSubgoal]:
    if workflow_kind == "finrisk":
        return [
            AgentSubgoal(
                objective=f"Identify filing-backed risks for: {user_goal}",
                tool_scope="company_research",
                required_evidence_types=["filing"],
                success_criteria=["at least one filing source is inspected"],
            ),
            AgentSubgoal(
                objective=f"Collect recent market evidence for: {user_goal}",
                tool_scope="finrisk_market",
                required_evidence_types=["web"],
                success_criteria=["market evidence includes source URLs"],
            ),
            AgentSubgoal(
                objective=f"Check graph paths and second-order exposure for: {user_goal}",
                tool_scope="finrisk_market",
                required_evidence_types=["graph_path"],
                success_criteria=["graph paths are accepted or uncertainty is recorded"],
            ),
        ]
    if workflow_kind == "supply_chain":
        return [
            AgentSubgoal(
                objective=f"Discover supplier candidates for: {user_goal}",
                tool_scope="supply_chain",
                required_evidence_types=["web", "filing"],
                success_criteria=["supplier candidates are evidence-backed"],
            ),
            AgentSubgoal(
                objective=f"Validate relation type and uncertainty for: {user_goal}",
                tool_scope="supply_chain",
                required_evidence_types=["web", "graph_path"],
                success_criteria=["confirmed edges have accepted evidence"],
            ),
        ]
    return [
        AgentSubgoal(
            objective=user_goal,
            tool_scope="company_research",
            required_evidence_types=["web"],
            success_criteria=["answer distinguishes evidence, inference, and uncertainty"],
        )
    ]


__all__ = [
    "AgentPlan",
    "AgentPlanner",
    "PlanStep",
    "PlanStepAction",
    "PlannerAgent",
]
