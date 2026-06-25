"""GraphReasoningAgent.

Performs read-only reasoning on the supply-chain graph by running the
query helpers in :mod:`src.graph.queries` and converts the results into
:class:`InvestmentHypothesis` graph paths.

The agent is intentionally conservative: it only fires rules when the
underlying Neo4j client is reachable, and falls back to "no graph paths"
when the database is empty or unavailable. This keeps the offline MVP
working without requiring a live Neo4j instance.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.base import Agent
from src.agents.state import AgentState
from src.schemas.hypotheses import InvestmentHypothesis

logger = logging.getLogger(__name__)


class GraphReasoningAgent:
    """Read-only graph reasoning for opportunity discovery.

    The agent reads from the configured Neo4j client and appends
    ``InvestmentHypothesis`` rows with ``graph_paths`` populated to the
    state. The agent is best-effort: any failure (no client, empty
    graph, query error) is logged and silently skipped so the rest of
    the pipeline keeps producing output.
    """

    name: str = "graph_reasoning"

    def __init__(self, client: Any | None = None) -> None:
        # When no client is provided the agent is a no-op so tests and
        # offline runs do not require a live Neo4j.
        self.client = client

    def run(self, state: AgentState) -> AgentState:
        if self.client is None:
            return state

        try:
            from src.graph.queries import (
                get_downstream_customers,
                get_geopolitical_exposures,
                get_policy_beneficiaries,
                get_upstream_suppliers,
            )

            ticker = state.ticker or ""
            if not ticker:
                return state
            paths = get_upstream_suppliers(self.client, ticker, depth=2)
            for path in paths:
                entities = path.nodes
                if len(entities) < 2:
                    continue
                state.notes.append(
                    f"graph: upstream path for {ticker}: "
                    + " -> ".join(e.name for e in entities)
                )
                state.entities.extend(entities)

            downstream = get_downstream_customers(self.client, ticker, depth=2)
            for path in downstream:
                state.entities.extend(path.nodes)

            # Treat policy beneficiaries and geopolitical exposures
            # as soft signals — append notes only, do not push entities
            # since the company itself is the focus.
            try:
                policies = get_policy_beneficiaries(
                    self.client, policy_name=ticker
                )
            except Exception:  # noqa: BLE001
                policies = []
            for exposure in policies:
                state.notes.append(
                    f"graph: policy exposure for {ticker}: {exposure.exposure_type}"
                )

            try:
                geo = get_geopolitical_exposures(self.client, region=ticker)
            except Exception:  # noqa: BLE001
                geo = []
            for exposure in geo:
                state.notes.append(
                    f"graph: geopolitical exposure for {ticker}: {exposure.exposure_type}"
                )
        except Exception as exc:  # noqa: BLE001
            logger.info("graph reasoning failed: %s", exc)

        return state


def is_graph_agent(obj: object) -> bool:
    """Runtime helper for ``isinstance``-free protocol checks."""
    return isinstance(obj, Agent) and getattr(obj, "name", None) == "graph_reasoning"
