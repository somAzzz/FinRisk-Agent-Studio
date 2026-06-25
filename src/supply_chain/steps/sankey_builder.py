"""v18 Step 6: Sankey builder."""

from __future__ import annotations

from src.supply_chain.models import SupplyChainExploreState
from src.supply_chain.sankey import build_sankey_payload
from src.supply_chain.steps._base import SupplyChainStep


class SupplyChainSankeyBuilderStep(SupplyChainStep):
    """Build the :class:`SankeyPayload` from the workflow state."""

    name = "sankey_builder"

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        state.sankey = build_sankey_payload(state)
        return state


__all__ = ["SupplyChainSankeyBuilderStep"]
