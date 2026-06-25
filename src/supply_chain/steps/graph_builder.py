"""v18 Step 5: graph builder.

In demo mode the graph is in-memory. Real mode can wire this
into the existing ``src.graph.writer`` (see spec 04).
"""

from __future__ import annotations

from src.supply_chain.models import SupplyChainExploreState
from src.supply_chain.steps._base import SupplyChainStep


class SupplyChainGraphBuilderStep(SupplyChainStep):
    """Hold the nodes / links in memory so the Sankey step can iterate them."""

    name = "graph_builder"

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        # v18 keeps the graph in ``state`` directly; a future
        # iteration can mirror it into Neo4j via
        # ``src.graph.writer.GraphWriter``.
        if not (state.request.demo_mode or state.request.cached_mode):
            state.fallback_events.append(
                "graph_builder:Neo4j wiring not yet enabled; using in-memory graph"
            )
        return state


__all__ = ["SupplyChainGraphBuilderStep"]
