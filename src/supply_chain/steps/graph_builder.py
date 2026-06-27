"""v18 Step 5: graph builder.

This step intentionally keeps the working graph in memory. Durable run
artifacts are handled by the run store; Neo4j receives a final Sankey
projection after evaluation, once canonical node ids and profiles exist.
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
        return state


__all__ = ["SupplyChainGraphBuilderStep"]
