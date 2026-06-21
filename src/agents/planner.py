"""Rule-based planner that turns an ``AgentState`` into an ``AgentPlan``."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agents.base import Agent
from src.agents.state import AgentState

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
