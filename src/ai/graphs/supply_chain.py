"""Sequential Pydantic Graph projection of the Supply Chain workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from pydantic_graph import Graph, GraphBuilder, StepContext

from src.supply_chain.models import SupplyChainExploreRequest, SupplyChainExploreState
from src.supply_chain.workflow import _default_steps, _resolve_store, _store_set


@dataclass(slots=True)
class SupplyChainGraphState:
    workflow: SupplyChainExploreState | None = None


@dataclass(slots=True)
class SupplyChainGraphDeps:
    steps: list[Any]
    store: Any


def build_supply_chain_graph() -> Graph[
    SupplyChainGraphState,
    SupplyChainGraphDeps,
    SupplyChainExploreState,
    SupplyChainExploreState,
]:
    """Build the fixed nine-step Supply Chain graph."""
    builder = GraphBuilder(
        name="supply-chain-workflow",
        state_type=SupplyChainGraphState,
        deps_type=SupplyChainGraphDeps,
        input_type=SupplyChainExploreState,
        output_type=SupplyChainExploreState,
    )

    @builder.step(node_id="initialize")
    async def initialize(
        ctx: StepContext[
            SupplyChainGraphState,
            SupplyChainGraphDeps,
            SupplyChainExploreState,
        ],
    ) -> None:
        ctx.state.workflow = ctx.inputs
        ctx.inputs.status = "running"
        await _store_set(ctx.deps.store, ctx.inputs)

    graph_steps = []
    for index, step_name in enumerate(
        [
            "product_resolver",
            "requirement_decomposer",
            "supplier_discovery",
            "evidence_normalizer",
            "graph_builder",
            "node_profile",
            "sankey_builder",
            "evaluator",
            "graph_projection",
        ]
    ):

        async def execute(
            ctx: StepContext[
                SupplyChainGraphState, SupplyChainGraphDeps, None
            ],
            *,
            step_index: int = index,
        ) -> None:
            state = _require_state(ctx.state)
            state = await ctx.deps.steps[step_index](state)
            ctx.state.workflow = state

        graph_steps.append(
            builder.step(execute, node_id=f"{index + 1:02d}_{step_name}")
        )

    @builder.step(node_id="finish")
    async def finish(
        ctx: StepContext[
            SupplyChainGraphState, SupplyChainGraphDeps, None
        ],
    ) -> SupplyChainExploreState:
        state = _require_state(ctx.state)
        await _store_set(ctx.deps.store, state)
        return state

    builder.add_edge(builder.start_node, initialize)
    previous = initialize
    for graph_step in graph_steps:
        builder.add_edge(previous, graph_step)
        previous = graph_step
    builder.add_edge(previous, finish)
    builder.add_edge(finish, builder.end_node)
    return builder.build()


async def run_supply_chain_graph(
    request: SupplyChainExploreRequest,
    *,
    steps: list[Any] | None = None,
    initial_state: SupplyChainExploreState | None = None,
    store: Any | None = None,
) -> SupplyChainExploreState:
    """Run the graph while preserving the existing store and state contract."""
    target_store = _resolve_store(store)
    state = initial_state or SupplyChainExploreState(
        run_id=f"sc-run-{uuid.uuid4().hex[:12]}", request=request
    )
    return await build_supply_chain_graph().run(
        state=SupplyChainGraphState(),
        deps=SupplyChainGraphDeps(
            steps=steps or _default_steps(), store=target_store
        ),
        inputs=state,
    )


def _require_state(state: SupplyChainGraphState) -> SupplyChainExploreState:
    if state.workflow is None:
        raise RuntimeError("Supply Chain graph was not initialized")
    return state.workflow


__all__ = [
    "SupplyChainGraphDeps",
    "SupplyChainGraphState",
    "build_supply_chain_graph",
    "run_supply_chain_graph",
]
