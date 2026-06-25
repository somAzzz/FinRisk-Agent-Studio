"""v18 Step 2: requirement decomposer.

In demo mode the step reads the fixture's pre-baked requirements
directly. In real mode the v18 spec 03 will layer an LLM
structured extractor on top of a rule fallback.
"""

from __future__ import annotations

from typing import Any

from src.supply_chain.fixtures import build_default_fixture
from src.supply_chain.models import (
    SupplyChainEdge,
    SupplyChainExploreState,
    SupplyChainNode,
)
from src.supply_chain.steps._base import SupplyChainStep


def _fixtures_by_product() -> dict[str, dict[str, Any]]:
    """Map the demo product to its requirements subgraph."""
    fixture = build_default_fixture()
    return {fixture["request"]["product_name"].lower(): fixture}


class SupplyChainRequirementDecomposerStep(SupplyChainStep):
    """Read the pre-baked requirement edges from the demo fixture.

    The decomposer is deliberately tiny: it consumes the demo
    fixture and emits the upstream requirements + edges. The
    real-mode adapter in spec 03 will replace this with an
    LLM-driven decomposition.
    """

    name = "requirement_decomposer"

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        if not (state.request.demo_mode or state.request.cached_mode):
            # Real mode is handled by the v18 spec 03 layer; for
            # now we return the same fixture and record a fallback
            # so the demo never silently returns empty.
            state.fallback_events.append(
                "requirement_decomposer:real mode not yet implemented; using fixture"
            )
        product_key = state.request.product_name.strip().lower()
        fixtures = _fixtures_by_product()
        if product_key not in fixtures:
            # Unknown product: record a warning so the evaluator
            # can downgrade the run to needs_review.
            state.warnings.append(
                f"no demo fixture for product {state.request.product_name!r}"
            )
            return state
        fixture = fixtures[product_key]
        # Merge nodes / links / evidence from the fixture into the
        # state. The product resolver already added the root
        # nodes; skip duplicates.
        existing_ids = {n.node_id for n in state.nodes}
        for raw in fixture["nodes"]:
            if raw["node_id"] in existing_ids:
                continue
            state.nodes.append(SupplyChainNode.model_validate(raw))
        existing_edges = {(e.source_node_id, e.target_node_id) for e in state.links}
        for raw in fixture["links"]:
            key = (raw["source_node_id"], raw["target_node_id"])
            if key in existing_edges:
                continue
            state.links.append(SupplyChainEdge.model_validate(raw))
        return state


__all__ = ["SupplyChainRequirementDecomposerStep"]
