"""v17 graph path backends.

The :class:`GraphPathBackend` protocol abstracts the storage layer
behind the path retriever. Two reference implementations are
provided:

- :class:`FixtureGraphBackend` — uses the in-memory fixture shipped
  with the project; the default for the demo / tests.
- :class:`Neo4jGraphBackend` — talks to a real Neo4j client; the
  ``client`` argument is duck-typed so unit tests can pass a fake.

Backend exceptions are converted into a guardrail finding by
:meth:`GraphReasoningSubsystem.run` so the workflow never crashes
because the graph store is offline.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from src.graph_reasoning.fixture_graph import EDGES as FIXTURE_EDGES
from src.graph_reasoning.fixture_graph import NODES as FIXTURE_NODES
from src.graph_reasoning.models import (
    CandidateGraphPath,
    GraphEdge,
    GraphEdgeMetadata,
    GraphNode,
    GraphQueryContext,
)
from src.graph_reasoning.path_retriever import retrieve_candidate_paths
from src.workflows.state import utcnow

logger = logging.getLogger(__name__)


@runtime_checkable
class GraphPathBackend(Protocol):
    """Pluggable storage layer for the path retriever.

    The protocol is intentionally narrow: a single ``retrieve`` call
    that takes a :class:`GraphQueryContext` and returns a list of
    candidate paths. Implementations may filter, expand, or rewrite
    paths however they wish, but every returned path must satisfy
    the v16 invariants (length 1-4, every edge has a confidence in
    ``[0, 1]``, etc.).
    """

    def retrieve(
        self, context: GraphQueryContext
    ) -> list[CandidateGraphPath]:
        ...


class FixtureGraphBackend:
    """Backend that serves the bundled in-memory fixture graph.

    The fixture is the same data the v15 graph reasoner used, so
    the demo workflow output is identical regardless of which
    backend is plugged in.

    Both ``nodes`` and ``edges`` default to the bundled fixture.
    Pass explicit empty lists to force an empty graph (used by
    unit tests that want to verify the ``no paths`` code path).
    """

    def __init__(
        self,
        *,
        nodes: list[GraphNode] | None = None,
        edges: list[GraphEdge] | None = None,
    ) -> None:
        self._nodes: list[GraphNode] = (
            list(FIXTURE_NODES) if nodes is None else list(nodes)
        )
        self._edges: list[GraphEdge] = (
            list(FIXTURE_EDGES) if edges is None else list(edges)
        )

    def retrieve(
        self, context: GraphQueryContext
    ) -> list[CandidateGraphPath]:
        return retrieve_candidate_paths(
            context, nodes=self._nodes, edges=self._edges
        )


class Neo4jGraphBackend:
    """Backend that queries a Neo4j client for candidate paths.

    The ``client`` argument is duck-typed: anything with a
    ``session()`` context manager that returns a session with a
    ``run(cypher, **params)`` method works. Unit tests pass a
    MagicMock; production code passes an instance of
    :class:`src.graph.client.Neo4jClient`.
    """

    CYPHER = (
        "MATCH path = (c:Company {ticker: $ticker})-[*1..3]-(n) "
        "WHERE ALL(r IN relationships(path) "
        "        WHERE coalesce(r.confidence, 0.0) >= 0.5) "
        "RETURN path "
        "LIMIT 50"
    )

    def __init__(self, client: Any) -> None:
        self._client = client

    def retrieve(
        self, context: GraphQueryContext
    ) -> list[CandidateGraphPath]:
        paths: list[CandidateGraphPath] = []
        with self._client.session() as session:
            result = session.run(self.CYPHER, ticker=context.ticker)
            for record in result:
                neo_path = record["path"]
                paths.append(self._from_neo4j(neo_path, context))
        return paths

    @staticmethod
    def _node_id(node: Any) -> str:
        if hasattr(node, "element_id"):
            return str(node.element_id)
        return str(node.id)

    @classmethod
    def _from_neo4j(
        cls, neo_path: Any, context: GraphQueryContext
    ) -> CandidateGraphPath:
        """Convert a Neo4j ``Path`` object to a v16 ``CandidateGraphPath``.

        The conversion is best-effort: nodes and edges are turned
        into the v16 Pydantic models. Properties that look like
        ``evidence_ids`` are passed through; everything else is
        stored in the ``properties`` / ``metadata`` bag.
        """
        nodes: list[GraphNode] = []
        for n in neo_path.nodes:
            nodes.append(
                GraphNode(
                    node_id=cls._node_id(n),
                    node_type=str(n.labels[0]) if n.labels else "Unknown",
                    label=str(n.get("label") or n.get("name") or "node"),
                    properties=dict(n),
                )
            )
        edges: list[GraphEdge] = []
        hop_count = 0
        for i, rel in enumerate(neo_path.relationships):
            edges.append(
                GraphEdge(
                    source_node_id=cls._node_id(rel.start_node),
                    target_node_id=cls._node_id(rel.end_node),
                    edge_type=str(rel.type),
                    metadata=GraphEdgeMetadata(
                        source="neo4j",
                        evidence_ids=list(rel.get("evidence_ids", [])),
                        confidence=float(rel.get("confidence", 0.5)),
                        extraction_method="imported",
                        created_at=utcnow(),
                    ),
                )
            )
            hop_count = i + 1
        return CandidateGraphPath(
            nodes=nodes,
            edges=edges,
            path_text=" → ".join(n.label for n in nodes),
            evidence_ids=list(
                {eid for e in edges for eid in e.metadata.evidence_ids}
            ),
            hop_count=hop_count,
        )


__all__ = [
    "FixtureGraphBackend",
    "GraphPathBackend",
    "Neo4jGraphBackend",
]
