"""v18 Step 3: supplier discovery.

In demo mode the supplier edges are already in the fixture (the
requirement decomposer pulls them in). Real mode will call the
existing ``SearchRouter`` and the v18 search-intent templates;
that layer is defined in spec 03.
"""

from __future__ import annotations

from src.supply_chain.models import SupplyChainExploreState
from src.supply_chain.steps._base import SupplyChainStep


class SupplyChainSupplierDiscoveryStep(SupplyChainStep):
    """Attach supplier edges to each requirement node.

    In demo mode the step is a no-op: the supplier edges are
    already part of the fixture consumed by the requirement
    decomposer. The real-mode adapter (spec 03) lives outside
    this skeleton so the v18 demo remains offline.
    """

    name = "supplier_discovery"

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        if not (state.request.demo_mode or state.request.cached_mode):
            state.fallback_events.append(
                "supplier_discovery:real mode not yet implemented; using fixture"
            )
        return state


__all__ = ["SupplyChainSupplierDiscoveryStep"]
