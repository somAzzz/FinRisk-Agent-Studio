"""Sequential Pydantic Graph projection of the FinRisk workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_graph import Graph, GraphBuilder, StepContext

from src.workflows.finrisk_workflow import (
    _CRITICAL_STEPS,
    DEFAULT_FIXTURE_DIR,
    _build_default_steps,
    _has_blocker,
)
from src.workflows.state import (
    FinRiskRequest,
    FinRiskWorkflowState,
    WorkflowTraceEvent,
    utcnow,
)


@dataclass(slots=True)
class FinRiskGraphState:
    """Mutable graph state containing the canonical workflow state."""

    workflow: FinRiskWorkflowState | None = None


@dataclass(slots=True)
class FinRiskGraphDeps:
    """Step dependencies and quality policy for one graph run."""

    steps: list[Any]
    quality_engine: Any | None = None
    quality_gated: bool = False


def build_finrisk_graph() -> Graph[
    FinRiskGraphState,
    FinRiskGraphDeps,
    FinRiskWorkflowState,
    FinRiskWorkflowState,
]:
    """Build a one-to-one sequential graph of the existing step pipeline."""
    builder = GraphBuilder(
        name="finrisk-workflow",
        state_type=FinRiskGraphState,
        deps_type=FinRiskGraphDeps,
        input_type=FinRiskWorkflowState,
        output_type=FinRiskWorkflowState,
    )

    @builder.step(node_id="initialize")
    async def initialize(
        ctx: StepContext[
            FinRiskGraphState, FinRiskGraphDeps, FinRiskWorkflowState
        ],
    ) -> None:
        ctx.state.workflow = ctx.inputs
        ctx.inputs.status = "running"

    graph_steps = []
    for index, step_name in enumerate(
        [
            "company_resolver",
            "filing_risk_extractor",
            "market_explorer",
            "evidence_normalizer",
            "risk_scorer",
            "lifecycle_classifier",
            "graph_reasoner",
            "report_generator",
            "evaluator",
        ]
    ):

        async def execute(
            ctx: StepContext[FinRiskGraphState, FinRiskGraphDeps, None],
            *,
            step_index: int = index,
        ) -> None:
            state = _require_state(ctx.state)
            step = ctx.deps.steps[step_index]
            if state.status == "failed":
                state.trace.append(
                    WorkflowTraceEvent(
                        step_name=step.name,
                        status="skipped",
                        started_at=utcnow(),
                        completed_at=utcnow(),
                        error="workflow aborted by earlier failure",
                    )
                )
                return
            if ctx.deps.quality_gated:
                if ctx.deps.quality_engine is None:
                    raise ValueError(
                        "quality_gated=True requires a quality_engine"
                    )
                from src.workflows.quality_gate import run_step_with_quality_gate

                state = await run_step_with_quality_gate(
                    state,
                    step=step,
                    engine=ctx.deps.quality_engine,
                )
                if _has_blocker(state):
                    if step.name in _CRITICAL_STEPS:
                        state.status = "failed"
                    else:
                        state.status = "running"
            else:
                state = await step(state)
            ctx.state.workflow = state

        graph_steps.append(
            builder.step(execute, node_id=f"{index + 1:02d}_{step_name}")
        )

    @builder.step(node_id="finish")
    async def finish(
        ctx: StepContext[FinRiskGraphState, FinRiskGraphDeps, None],
    ) -> FinRiskWorkflowState:
        return _require_state(ctx.state)

    builder.add_edge(builder.start_node, initialize)
    previous = initialize
    for graph_step in graph_steps:
        builder.add_edge(previous, graph_step)
        previous = graph_step
    builder.add_edge(previous, finish)
    builder.add_edge(finish, builder.end_node)
    return builder.build()


async def run_finrisk_graph(
    request: FinRiskRequest,
    *,
    fixture_path=None,
    steps: list[Any] | None = None,
    initial_state: FinRiskWorkflowState | None = None,
    run_id: str | None = None,
    quality_engine: Any | None = None,
    quality_gated: bool = False,
) -> FinRiskWorkflowState:
    """Run the graph and return the unchanged public workflow-state type."""
    import uuid

    fixture_path = fixture_path or (
        DEFAULT_FIXTURE_DIR / "aapl_demo_workflow.json"
    )
    state = initial_state or FinRiskWorkflowState(
        run_id=run_id or f"run-{uuid.uuid4().hex[:12]}",
        request=request,
    )
    deps = FinRiskGraphDeps(
        steps=steps or _build_default_steps(fixture_path),
        quality_engine=quality_engine,
        quality_gated=quality_gated,
    )
    return await build_finrisk_graph().run(
        state=FinRiskGraphState(), deps=deps, inputs=state
    )


def _require_state(state: FinRiskGraphState) -> FinRiskWorkflowState:
    if state.workflow is None:
        raise RuntimeError("FinRisk graph was not initialized")
    return state.workflow


__all__ = [
    "FinRiskGraphDeps",
    "FinRiskGraphState",
    "build_finrisk_graph",
    "run_finrisk_graph",
]
