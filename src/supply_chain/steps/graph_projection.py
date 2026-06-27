"""Final Neo4j projection for v18 supply-chain runs."""

from __future__ import annotations

import os
from typing import Any

from src.supply_chain.models import SupplyChainExploreState
from src.supply_chain.steps._base import SupplyChainStep


class SupplyChainGraphProjectionStep(SupplyChainStep):
    """Project the final Sankey artifact into Neo4j for cross-run queries."""

    name = "graph_projection"

    def __init__(self, *, graph_client: Any | None = None) -> None:
        super().__init__()
        if graph_client is not None:
            self._graph_client = graph_client
            self._graph_client_error = None
        else:
            self._graph_client, self._graph_client_error = _default_graph_client_from_env()

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        if state.sankey is None:
            state.fallback_events.append("graph_projection:sankey unavailable; skipped")
            return state
        if self._graph_client is None:
            if not (state.request.demo_mode or state.request.cached_mode):
                state.fallback_events.append(
                    "graph_projection:Neo4j client unavailable; "
                    f"{self._graph_client_error or 'no graph client configured'}; "
                    "run store remains source of truth"
                )
            return state
        try:
            from src.graph.supply_chain_writer import SupplyChainGraphWriter

            SupplyChainGraphWriter(self._graph_client).write_projection(state)
        except Exception as exc:
            state.fallback_events.append(
                "graph_projection:Neo4j write failed; "
                f"run store remains source of truth: {exc}"
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


__all__ = ["SupplyChainGraphProjectionStep"]
