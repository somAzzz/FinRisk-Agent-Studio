"""v18 Step 5: graph builder.

In demo mode the graph is in-memory. Real mode can wire this
into the existing ``src.graph.writer`` (see spec 04).
"""

from __future__ import annotations

import os
from typing import Any

from src.supply_chain.models import SupplyChainExploreState
from src.supply_chain.steps._base import SupplyChainStep


class SupplyChainGraphBuilderStep(SupplyChainStep):
    """Hold the nodes / links in memory so the Sankey step can iterate them."""

    name = "graph_builder"

    def __init__(self, *, graph_client=None) -> None:
        super().__init__()
        if graph_client is not None:
            self._graph_client = graph_client
            self._graph_client_error = None
        else:
            self._graph_client, self._graph_client_error = _default_graph_client_from_env()

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        if self._graph_client is None:
            if not (state.request.demo_mode or state.request.cached_mode):
                state.fallback_events.append(
                    (
                        "graph_builder:Neo4j client unavailable; "
                        f"{self._graph_client_error or 'no graph client configured'}; "
                        "using in-memory graph"
                    )
                )
            return state
        try:
            from src.graph.supply_chain_writer import SupplyChainGraphWriter

            SupplyChainGraphWriter(self._graph_client).write_graph(
                nodes=state.nodes,
                edges=state.links,
                evidence=state.evidence,
            )
        except Exception as exc:
            state.fallback_events.append(
                f"graph_builder:Neo4j write failed; using in-memory graph: {exc}"
            )
        return state


def _default_graph_client_from_env() -> tuple[Any | None, str | None]:
    password = os.environ.get("NEO4J_PASSWORD")
    if not password or password == "REPLACE_ME":
        return None, "NEO4J_PASSWORD is not set"
    try:
        from src.graph.client import Neo4jClient

        return Neo4jClient(), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


__all__ = ["SupplyChainGraphBuilderStep"]
