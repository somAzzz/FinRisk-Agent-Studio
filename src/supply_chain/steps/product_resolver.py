"""v18 Step 1: product resolver.

The step normalises the (company, product) input and emits the
root company + product nodes. In demo mode the resolver simply
slugs the names; in real mode it would call the existing
``TickerResolver`` to map OpenAI → ticker=None and to confirm
the product slug.
"""

from __future__ import annotations

from src.supply_chain.models import (
    SupplyChainExploreState,
    SupplyChainNode,
)
from src.supply_chain.steps._base import SupplyChainStep


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


class SupplyChainProductResolverStep(SupplyChainStep):
    """Emit the root company + product node for the request."""

    name = "product_resolver"

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        req = state.request
        company_id = f"company:{_slug(req.company_name or req.ticker or '')}"
        product_id = f"product:{_slug(req.product_name)}"

        company_node = SupplyChainNode(
            node_id=company_id,
            node_type="company",
            label=req.company_name or req.ticker or "Unknown",
            normalized_name=_slug(req.company_name or req.ticker or ""),
            ticker=req.ticker,
            depth=0,
            confidence=1.0,
        )
        product_node = SupplyChainNode(
            node_id=product_id,
            node_type="product",
            label=req.product_name,
            normalized_name=_slug(req.product_name),
            depth=1,
            parent_node_id=company_id,
            confidence=1.0,
        )
        # Replace any previous root nodes from a parent run.
        state.nodes = [
            n
            for n in state.nodes
            if n.node_id not in (company_id, product_id)
        ]
        state.nodes.extend([company_node, product_node])
        return state


__all__ = ["SupplyChainProductResolverStep"]
