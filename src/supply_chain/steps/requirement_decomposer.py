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

_GENERIC_REQUIREMENTS: tuple[tuple[str, str, str, float], ...] = (
    ("service:cloud-compute", "service", "Cloud compute", 1.0),
    ("component:gpu-accelerator", "component", "GPU accelerator", 0.9),
    ("component:cpu", "component", "CPU/server platform", 0.55),
    ("component:hbm-memory", "component", "HBM memory", 0.75),
    ("component:networking", "component", "Networking", 0.45),
    ("energy:datacenter-power", "energy", "Data center power", 0.75),
)


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
        product_key = state.request.product_name.strip().lower()
        fixtures = _fixtures_by_product()
        if (state.request.demo_mode or state.request.cached_mode) and product_key not in fixtures:
            # Unknown product: record a warning so the evaluator
            # can downgrade the run to needs_review.
            state.warnings.append(
                f"no demo fixture for product {state.request.product_name!r}"
            )
            return state
        if not (state.request.demo_mode or state.request.cached_mode):
            self._add_rule_requirements(state)
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

    @staticmethod
    def _add_rule_requirements(state: SupplyChainExploreState) -> None:
        """Add rule-based upstream requirements for real/cached discovery.

        These edges are intentionally marked ``hypothesized`` because
        they are product-architecture inferences. Supplier discovery
        later upgrades company edges to confirmed when search evidence
        exists.
        """
        product_id = f"product:{state.request.product_name.strip().lower().replace(' ', '-')}"
        existing_nodes = {n.node_id for n in state.nodes}
        existing_edges = {e.edge_id for e in state.links}
        for node_id, node_type, label, value in _GENERIC_REQUIREMENTS:
            if node_id not in existing_nodes:
                state.nodes.append(
                    SupplyChainNode(
                        node_id=node_id,
                        node_type=node_type,  # type: ignore[arg-type]
                        label=label,
                        normalized_name=label.lower(),
                        depth=1,
                        parent_node_id=product_id,
                        confidence=0.55,
                        metadata={"method": "rule_decomposer"},
                    )
                )
                existing_nodes.add(node_id)
            edge_id = f"sc-edge:{product_id}:{node_id}:requires"
            if edge_id in existing_edges:
                continue
            state.links.append(
                SupplyChainEdge(
                    edge_id=edge_id,
                    source_node_id=product_id,
                    target_node_id=node_id,
                    relation_type="hypothesized",
                    value=value,
                    confidence=0.55,
                    evidence_ids=[],
                    metadata={
                        "reason": "rule-based product architecture decomposition",
                        "method": "rule_decomposer",
                    },
                )
            )
            existing_edges.add(edge_id)


__all__ = ["SupplyChainRequirementDecomposerStep"]
