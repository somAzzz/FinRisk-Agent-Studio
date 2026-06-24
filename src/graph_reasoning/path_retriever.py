"""Candidate path retriever.

The v16 retriever walks the fixture graph (or, in future versions,
Neo4j) and returns every path that satisfies:

- starts at the company node,
- has length in ``[1, context.max_hops]``,
- only uses edges with type in ``context.allowed_edge_types``,
- every edge's confidence is at least ``min_edge_confidence``.

The retriever is intentionally bounded: a small fixture produces
at most a handful of candidate paths, well within MVP scope.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from src.graph_reasoning.fixture_graph import EDGES as FIXTURE_EDGES
from src.graph_reasoning.fixture_graph import NODES as FIXTURE_NODES
from src.graph_reasoning.models import (
    CandidateGraphPath,
    GraphEdge,
    GraphNode,
    GraphQueryContext,
)


MIN_EDGE_CONFIDENCE = 0.5


def _build_adjacency(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
) -> dict[str, list[GraphEdge]]:
    by_source: dict[str, list[GraphEdge]] = defaultdict(list)
    for edge in edges:
        by_source[edge.source_node_id].append(edge)
    return by_source


def _path_text(nodes: list[GraphNode]) -> str:
    return " → ".join(n.label for n in nodes)


def retrieve_candidate_paths(
    context: GraphQueryContext,
    *,
    nodes: list[GraphNode] | None = None,
    edges: list[GraphEdge] | None = None,
    min_edge_confidence: float = MIN_EDGE_CONFIDENCE,
) -> list[CandidateGraphPath]:
    """Walk the fixture (or supplied) graph and return candidate paths.

    The traversal is depth-first up to ``context.max_hops``. We
    exclude cycles by tracking the visited node set per branch.
    """
    nodes = list(nodes or FIXTURE_NODES)
    edges = list(edges or FIXTURE_EDGES)
    nodes_by_id = {n.node_id: n for n in nodes}
    adj = _build_adjacency(nodes, edges)
    allowed_edges = set(context.allowed_edge_types)
    # The fixture graph ships with a fixed set of edge types; the
    # context builder may not know about every one of them. The
    # retriever therefore treats an empty allowed-edges set as
    # "no restriction" (matches the v15 GraphReasonerStep default).
    no_restriction = not allowed_edges

    paths: list[CandidateGraphPath] = []

    def dfs(
        current: str,
        visited: set[str],
        node_chain: list[GraphNode],
        edge_chain: list[GraphEdge],
    ) -> None:
        if len(node_chain) > 1:
            paths.append(
                CandidateGraphPath(
                    nodes=list(node_chain),
                    edges=list(edge_chain),
                    path_text=_path_text(node_chain),
                    evidence_ids=_collect_evidence(edge_chain),
                    hop_count=len(node_chain) - 1,
                )
            )
        if len(node_chain) > context.max_hops:
            return
        for edge in adj.get(current, []):
            if not no_restriction and edge.edge_type not in allowed_edges:
                continue
            if edge.metadata.confidence < min_edge_confidence:
                continue
            if edge.target_node_id in visited:
                continue
            target = nodes_by_id.get(edge.target_node_id)
            if target is None:
                continue
            dfs(
                edge.target_node_id,
                visited | {edge.target_node_id},
                node_chain + [target],
                edge_chain + [edge],
            )

    company_node = nodes_by_id.get(context.company_id)
    if company_node is None:
        return []
    dfs(
        company_node.node_id,
        {company_node.node_id},
        [company_node],
        [],
    )
    return paths


def _collect_evidence(edges: Iterable[GraphEdge]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for edge in edges:
        for eid in edge.metadata.evidence_ids:
            if eid in seen:
                continue
            seen.add(eid)
            out.append(eid)
    return out


__all__ = ["MIN_EDGE_CONFIDENCE", "retrieve_candidate_paths"]
